from app.core.security import create_access_token, verify_password
from app.exceptions import AuthenticationError, ConflictError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def register(self, user: UserCreate) -> User:
        existing = self.repo.get_by_email(user.email)

        if existing:
            raise ConflictError(detail="Email already registered")

        return self.repo.create(user)

    def login(
        self,
        email: str,
        password: str,
    ) -> str:
        user = self.repo.get_by_email(email)

        if not user:
            raise AuthenticationError(detail="Invalid credentials")

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError(detail="Invalid credentials")

        return create_access_token({"sub": user.email})
