"""Add the canonical environmental_observations table.

Revision ID: b9d1e3f5a7c9
Revises: e8b4c6d9f1a3
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b9d1e3f5a7c9"
down_revision: Union[str, Sequence[str], None] = "e8b4c6d9f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environmental_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("dataset", sa.String(length=255), nullable=True),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("processing_level", sa.String(length=50), nullable=True),
        sa.Column("variable", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column("location_id", sa.Integer(),
                  sa.ForeignKey("monitored_locations.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("acquisition_time", sa.DateTime(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(), nullable=True),
        sa.Column("averaging_period", sa.String(length=20), nullable=False,
                  server_default="unknown"),
        sa.Column("resolution", sa.String(length=100), nullable=True),
        sa.Column("quality", sa.String(length=20), nullable=False,
                  server_default="unverified"),
        sa.Column("quality_flags", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_env_obs_variable_time", "environmental_observations",
                    ["variable", "observed_at"])
    op.create_index("ix_env_obs_source", "environmental_observations", ["source"])
    op.create_index("ix_env_obs_coords", "environmental_observations",
                    ["latitude", "longitude"])
    op.create_index(op.f("ix_environmental_observations_id"),
                    "environmental_observations", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_environmental_observations_id"),
                  table_name="environmental_observations")
    op.drop_index("ix_env_obs_coords", table_name="environmental_observations")
    op.drop_index("ix_env_obs_source", table_name="environmental_observations")
    op.drop_index("ix_env_obs_variable_time", table_name="environmental_observations")
    op.drop_table("environmental_observations")
