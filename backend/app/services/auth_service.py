"""Authentication service: registration, login, email verification, and refresh-token rotation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
    verify_password,
)
from app.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class AuthService:
    """Application-level authentication use-cases."""

    def __init__(
        self,
        repo: UserRepository,
        refresh_repo: RefreshTokenRepository | None = None,
    ):
        self.repo = repo
        self.refresh_repo = refresh_repo or RefreshTokenRepository(repo.db)

    # ------------------------------------------------------------------
    # Email verification helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _hash_verification_token(token: str) -> str:
        """Verification tokens are stored hashed, never in plaintext."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_verification_token() -> str:
        return secrets.token_urlsafe(32)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, user: UserCreate) -> tuple[User, str]:
        """Register a new user and return ``(user, verification_token)``.

        The account is created unverified; the caller is responsible for
        delivering the verification token to the user (via email in
        production, or returned to the client in development).
        """
        if self.repo.get_by_email(user.email):
            raise ConflictError(detail="Email already registered")

        db_user = self.repo.create(user)

        token = self.generate_verification_token()
        db_user.email_verification_token = self._hash_verification_token(token)
        db_user.email_verification_sent_at = datetime.now(timezone.utc)
        db_user = self.repo.commit_refresh(db_user)

        return db_user, token

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def login(self, email: str, password: str) -> dict:
        """Authenticate a user and return access + refresh tokens.

        Authentication additionally requires the account to be verified. A fresh
        refresh-token family is persisted for the newly created session.
        """
        user = self.repo.get_by_email(email)
        if not user:
            raise AuthenticationError(detail="Invalid credentials")

        if not user.is_verified:
            raise AuthenticationError(detail="Email not verified")

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError(detail="Invalid credentials")

        # Issue an access token and a fresh refresh token family.
        access_token = create_access_token({"sub": user.email})
        refresh_token, family_id, expires_at = create_refresh_token(user.id)
        self.refresh_repo.create(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            family_id=family_id,
            expires_at=expires_at,
        )
        self.refresh_repo.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # Refresh-token rotation
    # ------------------------------------------------------------------
    def refresh(self, refresh_token: str) -> dict:
        """Rotate a refresh token.

        On success the presented refresh token is revoked and a fresh
        access/refresh pair is issued within the same family lineage.

        Replaying a rotated (already-revoked) token is treated as theft: the
        entire family is revoked, invalidating every outstanding session.
        """
        token_hash = hash_token(refresh_token)
        row = self.refresh_repo.get_by_token_hash(token_hash)

        if row is None:
            raise AuthenticationError(detail="Invalid refresh token")

        if row.revoked_at is not None:
            # Reused token — burn the whole family.
            self.refresh_repo.revoke_family(row.family_id, datetime.now(timezone.utc))
            self.refresh_repo.commit()
            raise AuthenticationError(detail="Invalid refresh token")

        # Validate signature/expiry/type. Any failure here also burns the family
        # (the token is being replayed or tampered with).
        try:
            payload = decode_refresh_token(refresh_token)
        except HTTPException:
            self.refresh_repo.revoke_family(row.family_id, datetime.now(timezone.utc))
            self.refresh_repo.commit()
            raise AuthenticationError(detail="Invalid refresh token")

        now = datetime.now(timezone.utc)
        # `row.expires_at` is stored via SQLAlchemy DateTime, which holds a naive
        # datetime on SQLite (Postgres would return an aware one). Normalise to
        # UTC-aware so the comparison is valid on every backend.
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            self.refresh_repo.revoke_family(row.family_id, now)
            self.refresh_repo.commit()
            raise AuthenticationError(detail="Refresh token has expired")

        if payload.get("family") != row.family_id:
            self.refresh_repo.revoke_family(row.family_id, now)
            self.refresh_repo.commit()
            raise AuthenticationError(detail="Invalid refresh token")

        user = self.repo.get_by_id(row.user_id)
        if user is None:
            self.refresh_repo.revoke_family(row.family_id, now)
            self.refresh_repo.commit()
            raise AuthenticationError(detail="Invalid refresh token")

        new_access = create_access_token({"sub": user.email})
        new_refresh, family, expires_at = create_refresh_token(user.id, row.family_id)

        # Rotate: persist the replacement, revoke the presented one, commit atomically.
        self.refresh_repo.create(
            user_id=user.id,
            token_hash=hash_token(new_refresh),
            family_id=family,
            expires_at=expires_at,
        )
        self.refresh_repo.revoke(row.id, now)
        self.refresh_repo.commit()

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    def verify_email(self, token: str) -> User:
        """Confirm an account using a verification token."""
        token_hash = self._hash_verification_token(token)
        user = self.repo.get_by_verification_token(token_hash)
        if not user or user.is_verified:
            raise NotFoundError(detail="Invalid or expired verification token")

        user.is_verified = True
        user.email_verification_token = None
        user.email_verification_sent_at = None
        return self.repo.commit_refresh(user)

    def resend_verification(self, email: str) -> str:
        """Re-issue a verification token for an existing unverified account."""
        user = self.repo.get_by_email(email)
        if not user:
            raise NotFoundError(detail="User not found")

        token = self.generate_verification_token()
        user.email_verification_token = self._hash_verification_token(token)
        user.email_verification_sent_at = datetime.now(timezone.utc)
        self.repo.commit_refresh(user)

        return token
