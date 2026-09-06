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


def _patch_slowapi_starlette_compat() -> None:
    """Monkeypatch slowapi's `_inject_headers` to tolerate newer Starlette.

    slowapi 0.1.10's `sync_wrapper` passes the endpoint return value straight to
    `_inject_headers` on the Limiter class, which hard-fails with
    `parameter `response` must be an instance of starlette.responses.Response`
    when Starlette's response object is not an exact `Response` subclass. The
    rate-limit *decision* (allow/429) is made before this point and is
    unaffected — only the X-RateLimit-* header injection crashes. This patch
    defensively skips header injection when the response is not the expected
    type, preserving the actual rate limiting.
    """
    from slowapi.extension import Limiter as _Limiter

    _original_inject = _Limiter._inject_headers  # type: ignore[attr-defined]

    def _safe_inject(response, rate_limit, *args, **kwargs):
        try:
            from starlette.responses import Response as _StarletteResponse

            if not isinstance(response, _StarletteResponse):
                # Not a Response instance (e.g. a dict a sync endpoint returned
                # that FastAPI will wrap later). Skip header injection but return
                # the original value so the wrapper chain stays intact.
                return response
        except Exception:
            return response
        return _original_inject(response, rate_limit, *args, **kwargs)

    _Limiter._inject_headers = _safe_inject  # type: ignore[attr-defined]


_patch_slowapi_starlette_compat()


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
