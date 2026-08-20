"""Persistence for rotating refresh tokens.

Tokens are stored only as SHA-256 hashes. Repo methods mutate rows without
committing so the service can batch several changes into one transaction (e.g.
revoke the old token and persist its replacement atomically); call :meth:`commit`
when ready.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        token_hash: str,
        family_id: str,
        expires_at: datetime,
    ) -> RefreshToken:
        row = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

    def revoke(self, token_id: int, at: datetime) -> None:
        """Mark a single token revoked (it has been rotated)."""
        row = self.db.get(RefreshToken, token_id)
        if row is not None:
            row.revoked_at = at

    def revoke_family(self, family_id: str, at: datetime) -> None:
        """Revoke every non-revoked token in a family.

        Used when a rotated token is replayed (signals theft) or the active
        token is expired — the whole lineage is burned.
        """
        rows = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .all()
        )
        for row in rows:
            row.revoked_at = at

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()