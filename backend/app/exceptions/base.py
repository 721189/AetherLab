from typing import Optional


class AppError(Exception):
    """Base class for all application-specific errors."""

    status_code: int = 500
    detail: str = "Internal server error"
    code: str = "internal_error"

    def __init__(
        self,
        detail: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        self.detail = detail or self.detail
        self.code = code or self.code
        super().__init__(self.detail)


class AuthenticationError(AppError):
    """Authentication failed (missing/invalid credentials)."""

    status_code = 401
    detail = "Authentication failed"
    code = "authentication_error"


class AuthorizationError(AppError):
    """Authenticated user lacks permission to perform the action."""

    status_code = 403
    detail = "Insufficient permissions"
    code = "authorization_error"


class NotFoundError(AppError):
    """The requested resource does not exist."""

    status_code = 404
    detail = "Resource not found"
    code = "not_found"


class ValidationError(AppError):
    """Input payload failed validation."""

    status_code = 422
    detail = "Validation failed"
    code = "validation_error"


class ConflictError(AppError):
    """The request conflicts with the current state (e.g. duplicate)."""

    status_code = 409
    detail = "Resource conflict"
    code = "conflict_error"


class DatabaseError(AppError):
    """An unexpected database-level failure occurred."""

    status_code = 500
    detail = "Database error"
    code = "database_error"
