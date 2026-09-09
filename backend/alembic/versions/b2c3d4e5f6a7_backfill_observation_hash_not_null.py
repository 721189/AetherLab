"""Backfill observation_hash and enforce NOT NULL.

- Compute SHA-256 ``observation_hash`` for every existing row that currently
  has NULL (rows created before the dedup key was added).
- Then alter the column to NOT NULL so the database enforces what the
  model already declares (``nullable=False``).

Revision ID: b2c3d4e5f6a7
Revises: a4b6c8d0e2f4
Create Date: 2026-09-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a4b6c8d0e2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _compute_hash(row) -> str:
    """Recompute the SHA-256 dedup key for an existing row (portable)."""
    import hashlib
    import json

    provenance = row.provenance if isinstance(row.provenance, dict) else {}
    if provenance is None:
        provenance = {}
    canonical = json.dumps(
        {
            "source": row.source,
            "dataset": row.dataset,
            "product": row.product,
            "scene_id": provenance.get("scene_id") if isinstance(provenance, dict) else None,
            "variable": row.variable,
            "location": (
                round(float(row.latitude), 5) if row.latitude is not None else None,
                round(float(row.longitude), 5) if row.longitude is not None else None,
            ),
            "observed_at": row.observed_at.isoformat() if row.observed_at is not None else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # 1) Backfill NULL hashes using a portable Python-side computation
    #    (works on both SQLite and PostgreSQL).
    from app.models.environmental_observation import EnvironmentalObservationRecord

    session = Session(bind=bind)
    try:
        rows = (
            session.query(EnvironmentalObservationRecord)
            .filter(EnvironmentalObservationRecord.observation_hash.is_(None))
            .all()
        )
        for row in rows:
            row.observation_hash = _compute_hash(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # 2) Enforce NOT NULL — the model already declares nullable=False.
    #    SQLite doesn't support ALTER COLUMN, so use batch mode there.
    if is_postgresql:
        op.alter_column(
            "environmental_observations",
            "observation_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    else:
        # SQLite: recreate the table with the NOT NULL constraint.
        with op.batch_alter_table("environmental_observations") as batch_op:
            batch_op.alter_column(
                "observation_hash",
                existing_type=sa.String(length=64),
                nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "environmental_observations",
            "observation_hash",
            existing_type=sa.String(length=64),
            nullable=True,
        )
    else:
        with op.batch_alter_table("environmental_observations") as batch_op:
            batch_op.alter_column(
                "observation_hash",
                existing_type=sa.String(length=64),
                nullable=True,
            )
