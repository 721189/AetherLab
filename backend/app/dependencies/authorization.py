from fastapi import Depends

from app.dependencies.auth import get_current_user
from app.exceptions import AuthorizationError
from app.models.user import User


def require_role(*roles: str):
    """Return a dependency that enforces that the current user has one of the
    given roles."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = getattr(current_user, "role", None)
        if user_role not in roles:
            raise AuthorizationError(
                detail="Insufficient permissions for this operation"
            )
        return current_user

    return checker


def require_permission(permission: str):
    """Return a dependency that enforces the current user has the given
    permission. Roles are expanded to permissions here for simplicity."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        user_permissions = getattr(current_user, "permissions", None)
        if not user_permissions or permission not in user_permissions:
            raise AuthorizationError(
                detail=f"Missing required permission: {permission}"
            )
        return current_user

    return checker
