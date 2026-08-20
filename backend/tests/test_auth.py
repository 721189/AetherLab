import pytest


def valid_payload(email="Alice@Example.com", password="StrongPass123!"):
    return {"email": email, "password": password}


def register(client, **overrides):
    payload = valid_payload(**overrides)
    return client.post("/api/v1/auth/register", json=payload), payload


def register_and_login(client, **overrides):
    resp, payload = register(client, **overrides)
    assert resp.status_code == 201, resp.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], payload


class TestRegister:
    def test_register_creates_user(self, client):
        resp, payload = register(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == 1
        # email is normalized to lowercase
        assert body["email"] == "alice@example.com"
        # password must never be returned
        assert "hashed_password" not in body
        assert "password" not in body

    def test_register_rejects_weak_password(self, client):
        resp, _ = register(client, password="short")
        assert resp.status_code == 422

    def test_register_rejects_missing_uppercase(self, client):
        resp, _ = register(client, password="lowercase123!")
        assert resp.status_code == 422

    def test_register_duplicate_email(self, client):
        register(client)
        # normalizes differently but same email -> conflict
        resp, _ = register(client, email="ALICE@example.com")
        assert resp.status_code == 409

    def test_register_invalid_email(self, client):
        resp, _ = register(client, email="not-an-email")
        assert resp.status_code == 422


class TestLogin:
    def test_login_returns_bearer_token(self, client):
        _, payload = register(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]


class TestRefresh:
    def test_refresh_rotates_tokens(self, client):
        _, payload = register(client)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        ).json()
        old_refresh = login["refresh_token"]

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["refresh_token"]
        # The old token is rotated out and can no longer be used.
        assert body["refresh_token"] != old_refresh

        replay = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert replay.status_code == 401

    def test_refresh_rejects_garbage(self, client):
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.real.refresh.token"},
        )
        assert resp.status_code == 401

    def test_refresh_rejects_access_token(self, client):
        _, payload = register(client)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        body = login.json()
        # An access token must not be accepted where a refresh token is expected.
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": body["access_token"]},
        )
        assert resp.status_code == 401

    def test_login_wrong_password(self, client):
        _, payload = register(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "WrongPass123!"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "StrongPass123!"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client):
        token, payload = register_and_login(client)
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_me_without_token(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert resp.status_code == 401

    def test_me_with_expired_token(self, client):
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        from app.core.config import settings

        expired = jwt.encode(
            {
                "sub": "alice@example.com",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401


class TestVersioning:
    def test_endpoints_are_under_api_v1(self, client):
        paths = client.app.openapi()["paths"].keys()
        assert "/api/v1/auth/register" in paths
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/auth/me" in paths

    def test_request_id_header_returned(self, client):
        resp = client.get("/", headers={"X-Request-ID": "abc-123"})
        assert resp.headers.get("X-Request-ID") == "abc-123"