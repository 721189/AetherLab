"""Fix monitored_locations.enabled server_default for PostgreSQL.

`func.true()` renders as the literal string `true()` which is valid on
SQLite but a syntax error on PostgreSQL (`psycopg.errors.SyntaxError`).
This migration re-sets the column default to the SQL boolean literal
`true` so the PostgreSQL integration suite passes.  SQLite was
unaffected because it silently accepted `true()`.
"""

# revision identifiers, used by Alembic.
revision = "f7c9d1e3a5b8"
down_revision = "f6a8c0e2d4b6"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402  (must come after revision identifiers)
import sqlalchemy as sa  # noqa: E402


def upgrade() -> None:
    op.alter_column(
        "monitored_locations",
        "enabled",
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    # Restore the original (SQLite-valid, PostgreSQL-invalid) default.
    op.alter_column(
        "monitored_locations",
        "enabled",
        server_default=sa.text("true()"),
    )