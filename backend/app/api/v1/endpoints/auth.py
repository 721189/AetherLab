from fastapi import APIRouter, Depends, Request, Response

from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.rate_limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    EmailSchema,
    RefreshRequest,
    Token,
    UserCreate,
    UserLogin,
    UserRegisterResponse,
    UserResponse,
    VerificationResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=201,
    summary="Register a new user",
    description=(
        "Creates a new user account and emails a verification link. The raw "
        "verification token never appears in any API response — it exists "
        "only inside the emailed URL; only its SHA-256 hash is stored."
    ),
    response_description="User created; verification email dispatched",
)
@limiter.limit("3/minute")
def register(
    request: Request,
    user: UserCreate,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    db_user = service.register(user)
    return UserRegisterResponse(user=UserResponse.model_validate(db_user))


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and obtain access tokens",
    description=(
        "Exchanges valid credentials for an access token and a refresh token. "
        "Both are additionally set as HttpOnly cookies for browser clients "
        "(the JSON body is retained for non-browser API consumers)."
    ),
    response_description="Access and refresh tokens issued (+ HttpOnly cookies)",
)
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    user: UserLogin,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    tokens = service.login(user.email, user.password)
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return tokens


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh an access token",
    description=(
        "Issues a new access/refresh pair from a valid, non-revoked refresh "
        "token (body or HttpOnly cookie). Rotates the refresh-token family "
        "to prevent replay."
    ),
    response_description="Fresh access and refresh tokens (+ rotated cookies)",
)
@limiter.limit("5/minute")
def refresh(
    request: Request,
    response: Response,
    data: RefreshRequest | None = None,
    db=Depends(get_db),
):
    from app.core.cookies import REFRESH_TOKEN_COOKIE

    body_token = data.refresh_token if data else None
    token = body_token or request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not token:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )
    service = AuthService(UserRepository(db))
    tokens = service.refresh(token)
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return tokens


@router.post(
    "/logout",
    summary="Log out of the current browser session",
    description=(
        "Expires the HttpOnly auth cookies on the client. The presented "
        "refresh token (if any) is revoked server-side as well."
    ),
    response_description="Auth cookies cleared",
)
@limiter.limit("10/minute")
def logout(
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    from app.core.cookies import REFRESH_TOKEN_COOKIE

    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token:
        try:
            AuthService(UserRepository(db)).revoke_session(refresh_token)
        except Exception:
            pass  # logout must always succeed client-side
    clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.get(
    "/verify/{token}",
    response_model=VerificationResponse,
    summary="Verify a user's email address",
    description=(
        "Activates a user account using the token from the emailed link. "
        "Once verified the account can log in."
    ),
    response_description="Email marked as verified",
)
@limiter.limit("10/minute")
def verify_email(
    request: Request,
    token: str,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    service.verify_email(token)
    return {"message": "Email verified successfully"}


@router.post(
    "/resend-verification",
    response_model=VerificationResponse,
    summary="Resend the verification email",
    description=(
        "Sends a fresh verification link to an existing, unverified address. "
        "Rate-limited to prevent abuse."
    ),
    response_description="Verification email re-sent",
)
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    data: EmailSchema,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    service.resend_verification(data.email)
    return {"message": "Verification email sent"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
    description=(
        "Returns the profile of the user identified by the bearer token or "
        "the HttpOnly access-token cookie."
    ),
    response_description="The current user's profile",
)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
