"""TTL response cache for external environmental providers.

Every outbound call to OpenWeather/OpenAQ/NASA costs quota and money, so the
service layer consults this cache BEFORE hitting a provider:

    request -> cache hit? -> return cached payload
            -> miss?      -> provider call -> store with TTL

Cache keys are rounded to ~3 decimal places (~110 m) so nearby-but-not-identical
coordinates share entries without meaningful data loss.

Backend: Redis (shared across workers/replicas) when reachable, otherwise an
in-process dict for dev/tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Process-local fallback (dev/tests only).
_MEMORY_CACHE: Dict[str, Tuple[float, str]] = {}

_CLIENT = None
_CLIENT_CHECKED = False


def _redis():
    """Lazily obtain a Redis client; returns None when unavailable."""
    global _CLIENT, _CLIENT_CHECKED
    if not _CLIENT_CHECKED:
        _CLIENT_CHECKED = True
        try:
            import redis

            candidate = redis.Redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=1
            )
            candidate.ping()
            _CLIENT = candidate
        except Exception:
            _CLIENT = None
    return _CLIENT


def build_cache_key(provider: str, lat: float, lon: float, window: str = "") -> str:
    """Stable cache key: provider + coords rounded to ~110 m + time window."""
    rounded_lat = round(float(lat), 3)
    rounded_lon = round(float(lon), 3)
    raw = f"{provider}:{rounded_lat}:{rounded_lon}:{window}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"envcache:{provider}:{digest}"


def get_cached(key: str) -> Optional[Dict[str, Any]]:
    entry = None
    client = _redis()
    if client is not None:
        try:
            entry = client.get(key)
        except Exception as exc:
            logger.warning("Provider cache read failed (%s); treating as miss", exc)
    else:
        record = _MEMORY_CACHE.get(key)
        if record and record[0] > time.monotonic():
            entry = record[1]
        elif record:
            _MEMORY_CACHE.pop(key, None)

    if entry is None:
        return None
    try:
        return json.loads(entry)
    except (TypeError, ValueError):
        return None


def set_cached(key: str, payload: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
    ttl = max(1, int(ttl_seconds or settings.PROVIDER_CACHE_TTL_SECONDS))
    encoded = json.dumps(payload, default=str)
    client = _redis()
    if client is not None:
        try:
            client.set(key, encoded, ex=ttl)
            return
        except Exception as exc:
            logger.warning("Provider cache write failed (%s); using memory", exc)
    _MEMORY_CACHE[key] = (time.monotonic() + ttl, encoded)


def clear_all() -> None:
    """Test helper: wipe both backends."""
    _MEMORY_CACHE.clear()
    global _CLIENT_CHECKED
    client = _redis()
    if client is not None:
        try:
            keys = list(client.scan_iter("envcache:*"))
            if keys:
                client.delete(*keys)
        except Exception:
            pass