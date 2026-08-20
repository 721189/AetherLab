import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.dependencies.database import get_db
from app.main import app


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def override_get_db(db_engine):
    testing_session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
    )

    def _override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(override_get_db):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def disable_rate_limiting(override_get_db):
    """Turn off slowapi limits for the whole test session.

    Endpoints such as ``/auth/register`` are rate-limited (e.g. 3/minute) and
    the shared limiter uses in-memory storage keyed by a single TestClient
    remote address, so cumulative calls across many tests would otherwise hit
    429. The limiter is a hard requirement in production; tests disable it.
    """
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = True


def register(client, **overrides):
    """Legacy register function for tests that don't need verification."""
    payload = {"email": "test@example.com", "password": "StrongPass123!"}
    payload.update(overrides)
    resp = client.post("/api/v1/auth/register", json=payload)
    return resp, payload


def register_and_verify(client, email, password="StrongPass123!"):
    """Register a user and auto-verify them for tests that require login.

    Returns ``(access_token, payload)`` where payload is ``{"email", "password"}``.

    Verification is done through the real ``/api/v1/auth/verify/{token}``
    endpoint rather than by writing to the DB directly. The ``client`` fixture
    overrides ``get_db`` with an in-memory SQLite engine, so any direct
    ``SessionLocal()`` access would hit the real PostgreSQL database — using the
    endpoint guarantees the write lands in the same test DB and additionally
    exercises the real verification flow.
    """
    # Register (email is normalised to lowercase by the API).
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text
    verification_token = reg.json().get("verification_token")
    assert verification_token, "Expected a verification_token in register response"

    # Verify via the API against the same overridden test database.
    ver = client.get(f"/api/v1/auth/verify/{verification_token}")
    assert ver.status_code == 200, ver.text

    # Login now succeeds because the account is verified.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    access_token = body.get("access_token")
    assert access_token, "Login did not return an access_token"

    return access_token, {"email": email, "password": password}