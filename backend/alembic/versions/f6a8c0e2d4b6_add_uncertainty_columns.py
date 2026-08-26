"""Add explicit uncertainty-model columns to environmental_observations.

Revision ID: f6a8c0e2d4b6
Revises: d4e6f0a2b8c1
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6a8c0e2d4b6"
down_revision: Union[str, Sequence[str], None] = "d4e6f0a2b8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        "uncertainty",
        "confidence",
        "quality_score",
        "data_completeness",
    ):
        op.add_column(
            "environmental_observations",
            sa.Column(column, sa.Float(), nullable=True),
        )


def downgrade() -> None:
    for column in (
        "data_completeness",
        "quality_score",
        "confidence",
        "uncertainty",
    ):
        op.drop_column("environmental_observations", column)
