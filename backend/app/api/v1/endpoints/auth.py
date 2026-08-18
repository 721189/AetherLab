from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
def register(
    user: UserCreate,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    return service.register(user)


@router.post(
    "/login",
    response_model=Token,
)
def login(
    user: UserLogin,
    db=Depends(get_db),
):
    service = AuthService(UserRepository(db))
    token = service.login(user.email, user.password)
    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
