"""Add environmental_readings table

Revision ID: f7a3b2c5d9e1
Revises: e5f9a1c3d7b2
Create Date: 2026-08-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a3b2c5d9e1'
down_revision: Union[str, Sequence[str], None] = 'e5f9a1c3d7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'environmental_readings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_name', sa.String(length=255), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('feels_like', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Integer(), nullable=True),
        sa.Column('wind_speed', sa.Float(), nullable=True),
        sa.Column('wind_direction', sa.Float(), nullable=True),
        sa.Column('pressure', sa.Float(), nullable=True),
        sa.Column('uv_index', sa.Float(), nullable=True),
        sa.Column('weather_description', sa.String(length=255), nullable=True),
        sa.Column('aqi', sa.Integer(), nullable=True),
        sa.Column('pm25', sa.Float(), nullable=True),
        sa.Column('pm10', sa.Float(), nullable=True),
        sa.Column('no2', sa.Float(), nullable=True),
        sa.Column('o3', sa.Float(), nullable=True),
        sa.Column('co', sa.Float(), nullable=True),
        sa.Column('so2', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_environmental_readings_id'), 'environmental_readings', ['id'], unique=False)
    op.create_index(op.f('ix_environmental_readings_location_name'), 'environmental_readings', ['location_name'], unique=False)
    op.create_index(op.f('ix_environmental_readings_recorded_at'), 'environmental_readings', ['recorded_at'], unique=False)
    op.create_index(op.f('ix_environmental_readings_source'), 'environmental_readings', ['source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_environmental_readings_source'), table_name='environmental_readings')
    op.drop_index(op.f('ix_environmental_readings_recorded_at'), table_name='environmental_readings')
    op.drop_index(op.f('ix_environmental_readings_location_name'), table_name='environmental_readings')
    op.drop_index(op.f('ix_environmental_readings_id'), table_name='environmental_readings')
    op.drop_table('environmental_readings')