"""Production-correct canonical observations.

- Make timestamps timezone-aware (observed_at, acquisition_time, retrieved_at,
  created_at) — stored as UTC internally.
- Convert provenance / quality_flags to native JSON (JSONB on PostgreSQL).
- Add observation_hash (SHA-256 dedup key) with a UNIQUE index so Celery
  retries and re-fetched satellite scenes can never insert duplicates.

Revision ID: a4b6c8d0e2f4
Revises: f7c9d1e3a5b8
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a4b6c8d0e2f4"
down_revision: Union[str, Sequence[str], None] = "f6a8c0e2d4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cross-dialect JSON: native JSONB on PostgreSQL, plain JSON (TEXT) elsewhere.
JSON_COLUMN = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # 1. Timezone-aware timestamps (stored as UTC).
    _tz_columns = {
        "observed_at": "observed_at::timestamp with time zone",
        "acquisition_time": "acquisition_time::timestamp with time zone",
        "retrieved_at": "retrieved_at::timestamp with time zone",
        "created_at": "created_at::timestamp with time zone",
    }
    for col, using in _tz_columns.items():
        op.alter_column(
            "environmental_observations",
            col,
            type_=sa.DateTime(timezone=True),
            postgresql_using=using,
        )

    # 2) JSON-encoded provenance / quality_flags -> native JSON (JSONB on PG).
    op.alter_column(
        "environmental_observations",
        "provenance",
        type_=JSON_COLUMN,
        postgresql_using="provenance::jsonb",
    )
    op.alter_column(
        "environmental_observations",
        "quality_flags",
        type_=JSON_COLUMN,
        postgresql_using="quality_flags::jsonb",
    )

    # 3) Idempotency: observation_hash + UNIQUE index.
    op.add_column(
        "environmental_observations",
        sa.Column("observation_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_environmental_observations_observation_hash"),
        "environmental_observations",
        ["observation_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_environmental_observations_observation_hash"),
                  table_name="environmental_observations")
    op.drop_column("environmental_observations", "observation_hash")

    # Revert JSON columns back to plain strings.
    op.alter_column(
        "environmental_observations", "quality_flags",
        type_=sa.String(length=1024),
    )
    op.alter_column(
        "environmental_observations", "provenance",
        type_=sa.String(length=4096),
    )

    # Revert timestamps to timezone-naive.
    for col in ("observed_at", "acquisition_time", "retrieved_at", "created_at"):
        op.alter_column("environmental_observations", col, type_=sa.DateTime())