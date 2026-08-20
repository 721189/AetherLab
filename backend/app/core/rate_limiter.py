"""Shared rate-limiting configuration powered by slowapi.

The limiter reads the caller's IP via ``get_remote_address`` and is wired into the
FastAPI app in :mod:`app.main`. All endpoint modules import the single shared
``limiter`` instance so decorators stay consistent.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000/hour"],
    storage_uri="memory://",
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
