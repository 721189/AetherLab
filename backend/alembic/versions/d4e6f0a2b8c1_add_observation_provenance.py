"""Attach an immutable provenance column to environmental_observations.

Revision ID: d4e6f0a2b8c1
Revises: b9d1e3f5a7c9
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e6f0a2b8c1"
down_revision: Union[str, Sequence[str], None] = "b9d1e3f5a7c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "environmental_observations",
        sa.Column("provenance", sa.String(length=4096), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("environmental_observations", "provenance")
