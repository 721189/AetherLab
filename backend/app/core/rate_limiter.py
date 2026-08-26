"""Shared rate-limiting configuration powered by slowapi.

Storage backend resolution
--------------------------
The limiter state MUST be shared across all API replicas — with per-process
``memory://`` storage, three Render instances each allow the full quota.
Since Redis is already a hard dependency (Celery broker/backend), it is used
as the rate-limit store when reachable, with a graceful fallback to in-memory
storage for local development and tests without a running Redis.

All endpoint modules import the single shared ``limiter`` instance so
decorators stay consistent.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_storage_uri() -> str:
    """Prefer Redis-backed rate limiting; behaviour depends on APP_ENV.

    development/testing : Redis unreachable -> memory fallback (convenient).
    production          : Redis unreachable -> FAIL STARTUP. With per-process
                          memory storage, N replicas each grant the full quota
                          — silently multiplying every limit by N. That is an
                          unsafe deployment, so we refuse to boot instead.
    """
    redis_url = settings.REDIS_URL
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=1)
        client.ping()
        logger.info("Rate limiter using distributed Redis storage: %s", redis_url)
        return redis_url
    except Exception as exc:
        if settings.APP_ENV == "production":
            # Fail closed: an unenforceable rate limiter in a multi-instance
            # deployment is a security/cost incident waiting to happen.
            raise RuntimeError(
                "REDIS_URL is unreachable and APP_ENV=production: refusing to "
                "start with per-process rate-limit storage (limits would be "
                f"multiplied by the replica count). Fix Redis connectivity. "
                f"Underlying error: {exc.__class__.__name__}: {exc}"
            ) from exc
        logger.warning(
            "Redis unreachable (%s); rate limiter falling back to per-process "
            "memory storage. NOT suitable for multi-instance deployments.",
            exc.__class__.__name__,
        )
        return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000/hour"],
    storage_uri=_resolve_storage_uri(),
    headers_enabled=True,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a structured 429 response when a limit is exceeded."""
    retry_after = getattr(exc, "retry_after", None)
    return JSONResponse(
        status_code=429,
        headers=dict(exc.headers) if exc.headers else {},
        content={
            "detail": "Rate limit exceeded",
            "code": "rate_limit_exceeded",
            "retry_after": str(retry_after) if retry_after is not None else None,
        },
    )
