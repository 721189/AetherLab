"""Add the monitored_locations table.

Revision ID: e8b4c6d9f1a3
Revises: d6e7f8a9b0c1
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e8b4c6d9f1a3"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitored_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(op.f("ix_monitored_locations_user_id"), "monitored_locations", ["user_id"])
    op.create_index(op.f("ix_monitored_locations_enabled"), "monitored_locations", ["enabled"])


def downgrade() -> None:
    op.drop_index(op.f("ix_monitored_locations_enabled"), table_name="monitored_locations")
    op.drop_index(op.f("ix_monitored_locations_user_id"), table_name="monitored_locations")
    op.drop_table("monitored_locations")
