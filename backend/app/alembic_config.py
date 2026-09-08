"""Thin wrapper around the Alembic migration entry-point.

Provides ``run_migrations_up`` so that test suites and bootstrap scripts
can apply the full migration chain programmatically *without* shelling
out to the ``alembic`` CLI.  The migration configuration lives in
``alembic.ini`` / ``alembic/env.py`` and always uses
``settings.DATABASE_URL`` as the target — callers must therefore set
``DATABASE_URL`` (or ``TEST_DATABASE_URL`` + the env override below)
**before** importing this module.
"""

import os

from alembic import command
from alembic.config import Config

_ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def _resolve_config() -> Config:
    """Build an Alembic ``Config`` pointing at the correct database URL.

    ``alembic/env.py`` reads ``settings.DATABASE_URL``; in the test
    integration tier the URL is supplied via ``TEST_DATABASE_URL``, so
    we copy it into ``DATABASE_URL`` before any Alembic import happens.
    """
    # Mirror the CI pattern: TEST_DATABASE_URL takes precedence.
    if os.environ.get("TEST_DATABASE_URL") and not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

    cfg = Config(_ALEMBIC_INI)
    # Use an absolute path so migrations resolve correctly regardless of
    # the caller's CWD (tests run from the repo root, not from backend/).
    cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(_ALEMBIC_INI), "alembic"),
    )
    return cfg


def run_migrations_up() -> None:
    """Apply every pending migration (upgrade to ``head``)."""
    command.upgrade(_resolve_config(), "head")


def run_migrations_down() -> None:
    """Drop the entire schema (used for teardown in tests)."""
    command.downgrade(_resolve_config(), "base")
