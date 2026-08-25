from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.dependencies.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

security = HTTPBearer(auto_error=False)

# Name of the HttpOnly cookie holding the access token (set at /auth/login).
ACCESS_TOKEN_COOKIE = "access_token"


def _resolve_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    request: Optional[Request],
) -> Optional[str]:
    """Prefer the Authorization header; fall back to the HttpOnly cookie."""
    if credentials:
        return credentials.credentials
    if request is not None:
        return request.cookies.get(ACCESS_TOKEN_COOKIE)
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = _resolve_token(credentials, request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    email: str = payload.get("sub")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    repo = UserRepository(db)
    user = repo.get_by_email(email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    token = _resolve_token(credentials, request)
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None

    email: str = payload.get("sub")

    if not email:
        return None

    repo = UserRepository(db)
    return repo.get_by_email(email)
