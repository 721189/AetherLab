"""PostgreSQL-backed integration tests.

The main suite runs on in-memory SQLite (fast, hermetic) — but SQLite cannot
verify migrations, real constraints, server defaults or concurrency behaviour.
These tests run against a REAL PostgreSQL instance and are skipped unless the
``TEST_DATABASE_URL`` environment variable points at one.

Local usage:

    docker run -d --name aetherlab-test-pg -e POSTGRES_PASSWORD=test \
        -p 5433:5432 postgres:17-alpine
    TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:5433/postgres \
        pytest -m integration
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set",
    ),
]


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(os.environ["TEST_DATABASE_URL"])

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

    from app.alembic_config import run_migrations_up
    run_migrations_up()

    yield engine

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    SessionLocal = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def pg_client(pg_engine):
    from app.dependencies.database import get_db
    from app.main import app

    SessionLocal = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)


class TestRealDatabaseBehaviour:
    def test_unique_email_constraint_enforced_by_pg(self, pg_session):
        """SQLite's deferred uniqueness differs from PG; verify the DB itself."""
        from sqlalchemy.exc import IntegrityError

        from app.models.user import User

        pg_session.add(User(email="dup@example.com", hashed_password="x" * 60))
        pg_session.commit()
        pg_session.add(User(email="dup@example.com", hashed_password="y" * 60))
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()

    def test_monitored_locations_fk_cascade_on_real_pg(self, pg_session):
        from app.models.monitored_location import MonitoredLocation
        from app.models.user import User

        user = User(email="fk@example.com", hashed_password="x" * 60)
        pg_session.add(user)
        pg_session.commit()

        loc = MonitoredLocation(name="X", latitude=0, longitude=0, user_id=user.id)
        pg_session.add(loc)
        pg_session.commit()

        pg_session.delete(user)
        pg_session.commit()
        remaining = pg_session.query(MonitoredLocation).all()
        assert remaining == []

    def test_transaction_rollback_isolation(self, pg_session):
        from app.models.user import User

        pg_session.add(User(email="rb@example.com", hashed_password="x" * 60))
        pg_session.flush()
        pg_session.rollback()
        found = pg_session.query(User).filter_by(email="rb@example.com").first()
        assert found is None

    def test_refresh_token_rotation_flow_on_pg(self, pg_session):
        """The security-critical rotation flow against real PostgreSQL."""
        from datetime import datetime, timezone

        from app.core.security import create_refresh_token, hash_token
        from app.models.refresh_token import RefreshToken
        from app.models.user import User

        user = User(
            email="rot@example.com", hashed_password="x" * 60, is_verified=True
        )
        pg_session.add(user)
        pg_session.commit()

        refresh, family, expires_at = create_refresh_token(user.id)
        row = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            family_id=family,
            expires_at=expires_at,
        )
        pg_session.add(row)
        pg_session.commit()

        new_refresh, same_family, new_exp = create_refresh_token(user.id, family)
        row.revoked_at = datetime.now(timezone.utc)
        pg_session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(new_refresh),
                family_id=same_family,
                expires_at=new_exp,
            )
        )
        pg_session.commit()

        rows = pg_session.query(RefreshToken).filter_by(user_id=user.id).all()
        assert len(rows) == 2
        assert {r.family_id for r in rows} == {family}