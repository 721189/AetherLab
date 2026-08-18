import secrets
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, normalize_email
from app.core.security import hash_password


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        normalized_email = normalize_email(email)
        return (
            self.db.query(User)
            .filter(User.email == normalized_email)
            .first()
        )

    def create(self, user: UserCreate) -> User:
        db_user = User(
            email=user.email,
            hashed_password=hash_password(user.password),
        )

        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)

        return db_user

    @staticmethod
    def constant_time_compare(val1: str, val2: str) -> bool:
        return secrets.compare_digest(val1, val2)