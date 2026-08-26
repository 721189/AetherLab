"""HttpOnly cookie helpers for browser authentication.

Security model: tokens are delivered to browsers as HttpOnly cookies so
JavaScript can never read them (XSS cannot exfiltrate the session):

    access_token  : HttpOnly, Secure (prod), SameSite=Lax
    refresh_token : HttpOnly, Secure (prod), SameSite=Lax

SameSite=Lax is used for both because the frontend and API typically run on
different ports/origins in development; switch refresh to Strict in a
same-site deployment for extra CSRF hardening.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import settings

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


def _cookie_max_age(minutes: int) -> int:
    return minutes * 60


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Attach auth cookies to a login/refresh response."""
    from app.core.config import settings as s

    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=_cookie_max_age(s.ACCESS_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        secure=s.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        max_age=_cookie_max_age(s.REFRESH_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        secure=s.COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth",  # scoped: only ever sent to auth endpoints
    )


def clear_auth_cookies(response: Response) -> None:
    """Expire both auth cookies (logout)."""
    secure = settings.COOKIE_SECURE
    response.set_cookie(
        ACCESS_TOKEN_COOKIE, "", max_age=0, httponly=True,
        secure=secure, samesite="lax", path="/",
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE, "", max_age=0, httponly=True,
        secure=secure, samesite="lax", path="/api/v1/auth",
    )


# ---------------------------------------------------------------------------
# CSRF defence-in-depth (origin checking)
# ---------------------------------------------------------------------------

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _allowed_origins() -> set[str]:
    origins = {o.rstrip("/") for o in settings.CORS_ORIGINS}
    origins.add(settings.FRONTEND_BASE_URL.rstrip("/"))
    return origins


def is_cross_site_mutation(request: Request) -> bool:
    """True when a state-changing request uses cookie auth from a foreign origin.

    Browsers ALWAYS attach an Origin header to cross-site POSTs, so:
      * no Origin header      -> non-browser client (curl/service) -> allow
      * Origin in allow-list  -> first-party browser request       -> allow
      * foreign Origin        -> CSRF attempt                      -> block

    This complements SameSite=Lax (which already stops cross-site cookie
    attachment in modern browsers); the check catches legacy/embedded
    browsers and misconfigured subdomains.
    """
    if request.method.upper() not in UNSAFE_METHODS:
        return False
    # Header-based API clients are immune to CSRF by construction.
    if request.headers.get("authorization"):
        return False
    # Only cookie-authenticated mutations need the check.
    if not request.cookies.get(ACCESS_TOKEN_COOKIE):
        return False

    origin = request.headers.get("origin")
    if not origin:
        return False  # non-browser clients don't send Origin
    return origin.rstrip("/") not in _allowed_origins()

