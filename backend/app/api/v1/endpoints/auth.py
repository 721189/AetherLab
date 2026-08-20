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
)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
