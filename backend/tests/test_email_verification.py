"""Tests for the email-based verification flow and HttpOnly cookie sessions."""

from tests.conftest import register_and_verify


class TestVerificationEmailFlow:
    def test_token_only_delivered_by_email(self, client):
        """The raw verification token exists ONLY inside the emailed link."""
        from app.services.email_provider import OUTBOX

        outbox_before = len(OUTBOX)
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "password": "StrongPass123!"},
        )
        assert reg.status_code == 201
        # Never in the API response...
        assert "verification_token" not in reg.json()
        # ...only in the email body's verification URL.
        assert len(OUTBOX) == outbox_before + 1
        sent = OUTBOX[-1]
        assert sent["to"] == "bob@example.com"
        assert "verify-email?token=" in sent["body"]

    def test_stored_token_is_hashed_not_plaintext(self, client, db_session):
        from app.models.user import User

        client.post(
            "/api/v1/auth/register",
            json={"email": "hash@example.com", "password": "StrongPass123!"},
        )
        user = db_session.query(User).filter_by(email="hash@example.com").one()
        assert user.email_verification_token is not None
        # A SHA-256 hex digest is exactly 64 chars; plaintext tokens aren't.
        assert len(user.email_verification_token) == 64

    def test_resend_verification_does_not_leak_token(self, client):
        from app.services.email_provider import OUTBOX

        # Register an unverified account first.
        client.post(
            "/api/v1/auth/register",
            json={"email": "carol@example.com", "password": "StrongPass123!"},
        )
        outbox_before = len(OUTBOX)
        resp = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "carol@example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Verification email sent"
        assert "verification_token" not in body
        assert len(OUTBOX) == outbox_before + 1

    def test_emailed_link_completes_verification(self, client):
        from app.services.email_provider import OUTBOX

        client.post(
            "/api/v1/auth/register",
            json={"email": "dave@example.com", "password": "StrongPass123!"},
        )
        token = OUTBOX[-1]["body"].split("token=")[1].splitlines()[0].strip()
        resp = client.get(f"/api/v1/auth/verify/{token}")
        assert resp.status_code == 200
        # The token is single-use.
        replay = client.get(f"/api/v1/auth/verify/{token}")
        assert replay.status_code == 404


class TestHttpOnlyCookieSessions:
    def test_login_sets_httponly_cookies(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 200
        cookie_header = resp.headers["set-cookie"]
        assert "access_token=" in cookie_header
        assert "refresh_token=" in cookie_header
        assert "httponly" in cookie_header.lower()
        assert "samesite=lax" in cookie_header.lower()
        # Refresh cookie is path-scoped to auth endpoints only.
        assert "/api/v1/auth" in cookie_header

    def test_me_accepts_cookie_without_bearer_header(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        # TestClient persists cookies automatically; no Authorization header.
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"

    def test_logout_clears_cookies(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        # Expired cookies come back with Max-Age=0.
        assert "Max-Age=0" in logout.headers["set-cookie"]

    def test_refresh_via_cookie(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        login = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        old_refresh = login.json()["refresh_token"]

        # No body — the refresh token comes from the HttpOnly cookie.
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["access_token"]
        assert new_tokens["refresh_token"] != old_refresh

    def test_refresh_without_any_token_is_401(self, client):
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


class TestEmailProviderAbstraction:
    def test_factory_returns_console_when_no_resend_key(self, monkeypatch):
        from app.core.config import settings
        from app.services.email_provider import (
            ConsoleEmailProvider,
            get_email_provider,
        )

        monkeypatch.setattr(settings, "RESEND_API_KEY", "")
        provider = get_email_provider()
        assert isinstance(provider, ConsoleEmailProvider)

    def test_factory_returns_resend_when_key_set(self, monkeypatch):
        from app.core.config import settings
        from app.services.email_provider import ResendEmailProvider, get_email_provider

        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        provider = get_email_provider()
        assert isinstance(provider, ResendEmailProvider)

    def test_console_provider_captures_outbox_entry(self):
        import asyncio

        from app.services.email_provider import OUTBOX, ConsoleEmailProvider

        before = len(OUTBOX)
        asyncio.run(ConsoleEmailProvider().send_verification_email("x@y.z", "tok123"))
        entry = OUTBOX[before]
        assert entry["to"] == "x@y.z"
        assert "tok123" in entry["body"]
