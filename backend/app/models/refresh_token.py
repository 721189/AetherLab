from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """A long-lived, rotating refresh token persisted as a SHA-256 hash.

    All tokens in one ``family_id`` form a rotation lineage. When a token is
    used to refresh it is revoked and replaced with a new one in the same
    family. Replaying an already-revoked token signals theft and revokes the
    whole family.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Rotation lineage. Multiple rows share a family across refreshes; there is
    # exactly one non-revoked (active) row per family at any time.
    family_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # SHA-256 hex digest (64 chars) — never store the raw token.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # When non-null the token has been rotated into this replacement row.
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_tokens.id"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="refresh_tokens",
    )

    def __repr__(self) -> str:
        revoked = "active" if self.revoked_at is None else f"revoked@{self.revoked_at}"
        return (
            f"<RefreshToken(id={self.id}, user_id={self.user_id}, "
            f"family={self.family_id!r}, {revoked})>"
        )