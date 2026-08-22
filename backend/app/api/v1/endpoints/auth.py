from fastapi import APIRouter, Depends, Request

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
        "Creates a new user account and returns a verification token. The "
        "account is inactive until the email is verified via "
        "`GET /auth/verify/{token}`. Duplicate emails are rejected."
    ),
    response_description="User created successfully with verification token",
)
@limiter.limit("3/minute")
def register(
    request: Request,
    user: UserCreate,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    db_user, token = service.register(user)
    return UserRegisterResponse(
        user=UserResponse.model_validate(db_user),
        verification_token=token,
    )


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and obtain access tokens",
    description=(
        "Exchanges valid credentials for an access token and a refresh token. "
        "The refresh token can be used later at `POST /auth/refresh`."
    ),
    response_description="Access and refresh tokens issued",
)
@limiter.limit("5/minute")
def login(
    request: Request,
    user: UserLogin,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    return service.login(user.email, user.password)


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh an access token",
    description=(
        "Issues a new access/refresh token pair from a valid, non-revoked "
        "refresh token. Rotates the refresh token family to prevent replay."
    ),
    response_description="Fresh access and refresh tokens",
)
@limiter.limit("5/minute")
def refresh(
    request: Request,
    data: RefreshRequest,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    return service.refresh(data.refresh_token)


@router.get(
    "/verify/{token}",
    response_model=VerificationResponse,
    summary="Verify a user's email address",
    description=(
        "Activates a user account using the token issued at registration. "
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
    summary="Resend the email verification token",
    description=(
        "Sends a fresh verification token to an existing, unverified email "
        "address. Rate-limited to prevent abuse."
    ),
    response_description="New verification token issued",
)
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    data: EmailSchema,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    token = service.resend_verification(data.email)
    return {"message": "Verification email sent", "verification_token": token}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
    description="Returns the profile of the user identified by the bearer token.",
    response_description="The current user's profile",
)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
