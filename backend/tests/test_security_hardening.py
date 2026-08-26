"""Tests for the security-hardening batch (items 11-20 review)."""

from tests.conftest import register_and_verify


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestImmutableIdentity:
    def test_jwt_sub_is_user_id_not_email(self, client):
        token, payload = register_and_verify(client, "alice@example.com")
        from app.core.config import settings
        from jose import jwt

        claims = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"]
        )
        assert claims["sub"] == "1"  # immutable numeric ID
        assert "@" not in claims["sub"]

    def test_legacy_email_sub_is_rejected(self, client):
        """A forged email-sub token from the old scheme must not authenticate."""
        _, payload = register_and_verify(client, "alice@example.com")
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        from app.core.config import settings

        stale = jwt.encode(
            {
                "sub": "alice@example.com",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        resp = client.get("/api/v1/auth/me", headers=auth(stale))
        assert resp.status_code == 401


class TestBrowserLogin:
    def test_login_browser_returns_no_tokens(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        resp = client.post(
            "/api/v1/auth/login/browser",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"message": "Authenticated"}
        # Cookies ARE set; tokens are NOT in the response.
        assert "access_token=" in resp.headers["set-cookie"]
        assert "access_token" not in body and "refresh_token" not in body


class TestCsrfOriginCheck:
    def test_cross_site_cookie_mutation_is_rejected(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        evil = client.post(
            "/api/v1/projects/",
            json={"name": "csrf"},
            headers={"Origin": "https://evil.example"},
            cookies={"access_token": client.cookies.get("access_token")},
        )
        assert evil.status_code == 403
        assert evil.json()["code"] == "csrf_rejected"

    def test_first_party_origin_is_allowed(self, client):
        _, payload = register_and_verify(client, "alice@example.com")
        client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        ok = client.post(
            "/api/v1/projects/",
            json={"name": "fine"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert ok.status_code == 201


class TestSatelliteAPI:
    def _login(self, client):
        return register_and_verify(client, "sat@example.com")[0]

    def test_scene_search_endpoint(self, client, monkeypatch):
        from unittest.mock import AsyncMock

        from app.services.environmental import ProviderRegistry
        from app.services.providers.satellite import SatelliteScene

        provider = ProviderRegistry.get("nasa")
        monkeypatch.setattr(
            provider,
            "search",
            AsyncMock(return_value=[
                SatelliteScene(
                    scene_id="POWER-2026-08-24", source="nasa", dataset="POWER",
                    product="reanalysis-daily-point", processing_level="L3",
                    resolution="55km",
                    acquisition_time=__import__("datetime").datetime(
                        2026, 8, 24, tzinfo=__import__("datetime").timezone.utc
                    ),
                )
            ]),
        )

        token = self._login(client)
        resp = client.get(
            "/api/v1/satellite/scenes",
            params={"lat": 28.6, "lon": 77.2, "source": "nasa"},
            headers=auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["scenes"][0]["scene_id"] == "POWER-2026-08-24"

    def test_unknown_source_is_400_not_500(self, client):
        token = self._login(client)
        resp = client.get(
            "/api/v1/satellite/scenes",
            params={"lat": 0, "lon": 0, "source": "nope"},
            headers=auth(token),
        )
        assert resp.status_code == 400

    def test_requires_authentication(self, client):
        resp = client.get(
            "/api/v1/satellite/scenes", params={"lat": 0, "lon": 0}
        )
        assert resp.status_code == 401