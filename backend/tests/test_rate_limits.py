#!/usr/bin/env python































































































































































































































































"""Rate-limit-specific tests.

Covers per-user provider quotas and request-rate limiting behavior.
"""

from __future__ import annotations

import time

import pytest

from app.core.rate_limiter import (
    PerUserRateLimiter,
    RateLimitExceededError,
    check_provider_quota,
    get_limiter_key,
    get_rate_limit_headers,
    limiter,
)
from app.models.user import User
from app.schemas.rate_limit import ProviderQuota, ProviderQuotaStatus


class TestLimiterKey:
    def test_user_based_key(self):
        user = User(id=1, email="a@example.com")
        key = get_limiter_key(user, "provider_calls")
        assert key == "user:1:provider_calls"

    def test_unauthenticated_key(self):
        key = get_limiter_key(None, "provider_calls")
        assert key.startswith("anon:")

    def test_various_resources(self):
        user = User(id=42, email="u@example.com")
        assert get_limiter_key(user, "llm_tokens") == "user:42:llm_tokens"
        assert get_limiter_key(user, "satellite_jobs") == "user:42:satellite_jobs"
        assert get_limiter_key(user, "storage_bytes") == "user:42:storage_bytes"


class TestPerUserRateLimiter:
    def test_basic_allowance(self):
        limiter = PerUserRateLimiter(key="test:1", max_calls=5, period_seconds=60)
        for _ in range(5):
            assert limiter.allow() is True

    def test_exceeds_max(self):
        limiter = PerUserRateLimiter(key="test:exceed", max_calls=2, period_seconds=60)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False

    def test_allowance_reset_on_period(self):
        limiter = PerUserRateLimiter(key="test:reset", max_calls=1, period_seconds=2)
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(2.1)
        assert limiter.allow() is True

    def test_quota_remaining(self):
        limiter = PerUserRateLimiter(key="test:rem", max_calls=5, period_seconds=60)
        for _ in range(3):
            limiter.allow()
        assert limiter.remaining() == 2


class TestProviderQuota:
    @pytest.fixture
    def user(self):
        return User(id=1, email="u@example.com")



    def test_under_quota_allows(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=50, period_seconds=3600
        )
        check_provider_quota(user, quota)

    def test_over_quota_blocks(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=150, period_seconds=3600
        )
        with pytest.raises(RateLimitExceededError) as exc_info:
            check_provider_quota(user, quota)
        assert "openaq" in str(exc_info.value)

    def test_quota_status_under(self, user):
        quota = ProviderQuota(
            provider="openweather", max_calls=50, used=20, period_seconds=3600
        )
        status = ProviderQuotaStatus.from_quota(quota, user)
        assert status.allowed is True

    def test_quota_status_exhausted(self, user):
        quota = ProviderQuota(
            provider="openweather", max_calls=50, used=50, period_seconds=3600
        )
        status = ProviderQuotaStatus.from_quota(quota, user)
        assert status.allowed is False








class TestRateLimitHeaders:
    def test_x_rate_limit_headers_present(self):
        headers = get_rate_limit_headers(
            limit=100, remaining=80, reset_epoch=int(time.time()) + 30
        )
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "80"


class TestSlowapiLimiter:
    def test_limiter_is_configured(self):
        assert limiter is not None

    def test_default_limit_applied(self):
        assert limiter._default_limit is not None


class TestRateLimitedEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        return TestClient(create_app())

    def test_health_unlimited(self, client):
        resp = client.get("/health/live")
        assert resp.status_code in (200, 503)

    def test_auth_route_exists(self, client):
        resp = client.post("/auth/login", json={"email": "a@b.com", "password": "x"})
        assert resp.status_code in (400, 401, 422)

    def test_period_allows_renewal(self):
        limiter = PerUserRateLimiter(key="test:r", max_calls=2, period_seconds=1)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(1.1)
        assert limiter.allow() is True

    def test_multiple_users_isolated(self):
        a = PerUserRateLimiter(key="user:a", max_calls=1, period_seconds=60)
        b = PerUserRateLimiter(key="user:b", max_calls=1, period_seconds=60)
        assert a.allow() is True
        assert b.allow() is True
        assert a.allow() is False
        assert b.allow() is True

"""Rate-limit-specific tests.

Covers per-user provider quotas and request-rate limiting behavior.

The current implementation uses FastAPI + slowapi (limits) for endpoint-level
rate limits plus a custom PerUserRateLimiter concept for provider-level
quotas. These tests validate the contract; provider-level quota enforcement
is exercised against a real backend in the optional integration tier.

"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.rate_limiter import (
    PerUserRateLimiter,
    RateLimitExceededError,
    check_provider_quota,
    get_limiter_key,
    get_rate_limit_headers,
    limiter,
)
from app.models.user import User
from app.schemas.rate_limit import ProviderQuota, ProviderQuotaStatus


# ---------------------------------------------------------------------------
# Limiter key derivation
# ---------------------------------------------------------------------------

class TestLimiterKey:
    def test_user_based_key(self):
        user = User(id=1, email="a@example.com")
        key = get_limiter_key(user, "provider_calls")
        assert key == "user:1:provider_calls"

    def test_unauthenticated_key(self):
        key = get_limiter_key(None, "provider_calls")
        assert key.startswith("anon:")

    def test_various_resources(self):
        user = User(id=42, email="u@example.com")
        assert get_limiter_key(user, "llm_tokens") == "user:42:llm_tokens"
        assert get_limiter_key(user, "satellite_jobs") == "user:42:satellite_jobs"
        assert get_limiter_key(user, "storage_bytes") == "user:42:storage_bytes"


# ---------------------------------------------------------------------------
# PerUserRateLimiter
# ---------------------------------------------------------------------------

class TestPerUserRateLimiter:
    def test_basic_allowance(self):
        limiter = PerUserRateLimiter(
            key="test:1",
            max_calls=5,
            period_seconds=60,
        )
        for _ in range(5):
            assert limiter.allow() is True

    def test_exceeds_max(self):
        limiter = PerUserRateLimiter(key="test:exceed", max_calls=2, period_seconds=60)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False

    def test_allowance_reset_on_period(self):
    def test_exceeds_max(self):
    def test_exceeds_max(self):
        limiter = PerUserRateLimiter(key="test:exceed", max_calls=2, period_seconds=60)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False



    def test_allowance_reset_on_period(self):
        limiter = PerUserRateLimiter(key="test:reset", max_calls=1, period_seconds=2)
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(2.1)
        assert limiter.allow() is True

    def test_quota_remaining(self):
        limiter = PerUserRateLimiter(key="test:rem", max_calls=5, period_seconds=60)
        for _ in range(3):
            limiter.allow()
        remaining = limiter.remaining()
        assert remaining == 2


# ---------------------------------------------------------------------------
    def test_under_quota_allows(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=50, period_seconds=3600
        )
        check_provider_quota(user, quota)  # should not raise

    def test_over_quota_blocks(self, user):
# Provider quota check
# ---------------------------------------------------------------------------

class TestProviderQuotaCheck:
    @pytest.fixture
    def user(self):
        return User(id=7, email="t@e.c")

    def test_under_quota_allows(self, user):
    def test_over_quota_blocks(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=100, period_seconds=3600
        )
        with pytest.raises(RateLimitExceededError) as exc_info:
            check_provider_quota(user, quota)
        assert "openaq" in str(exc_info.value)

        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=50, period_seconds=3600
        )
        assert check_provider_quota(user, quota) is True

    def test_over_quota_blocks(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=100, period_seconds=3600
        )
        with pytest.raises(RateLimitExceededError):
            check_provider_quota(user, quota)

    def test_quota_error_wrapped(self, user):
        quota = ProviderQuota(
            provider="openaq", max_calls=100, used=100, period_seconds=3600
        )
        with pytest.raises(RateLimitExceededError) as exc_info:
            check_provider_quota(user, quota)
        assert "openaq" in str(exc_info.value)

    def test_quota_status_under(self, user):
        quota = ProviderQuota(
            provider="openweather", max_calls=50, used=20, period_seconds=3600
        )
        status = ProviderQuotaStatus.from_quota(quota, user)
        assert status.allowed is True
        assert status.remaining > 0

    def test_quota_status_exhausted(self, user):
        quota = ProviderQuota(
            provider="openweather", max_calls=50, used=50, period_seconds=3600
        )
        status = ProviderQuotaStatus.from_quota(quota, user)
        assert status.allowed is False


# ---------------------------------------------------------------------------
# Rate limit response headers
# ---------------------------------------------------------------------------

class TestRateLimitHeaders:
    def test_x_rate_limit_headers_present(self):
        headers = get_rate_limit_headers(
            limit=100, remaining=80, reset_epoch=int(time.time()) + 30
        )
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "80"
        assert "X-RateLimit-Reset" in headers


# ---------------------------------------------------------------------------
# slowapi limiter integration
# ---------------------------------------------------------------------------

class TestSlowapiLimiter:
    def test_limiter_is_configured(self):
        assert limiter is not None

    def test_default_limit_applied(self):
        # The global limiter default limit should be a numeric value or string.
        assert limiter._default_limit is not None


# ---------------------------------------------------------------------------
# Endpoints with rate limiting
# ---------------------------------------------------------------------------

class TestRateLimitedEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        return TestClient(create_app())

    def test_health_unlimited(self, client):
        # Health endpoints should not be rate-limited.
        resp = client.get("/health/live")
        assert resp.status_code in (200, 503)

    def test_auth_rate_limited_route_exists(self, client):
        # Login/register endpoints should enforce rate limits at the
        # infrastructure level; this merely verifies the route exists and
        # responds.
        resp = client.post("/auth/login", json={"email": "a@b.com", "password": "x"})
        assert resp.status_code in (400, 401, 422)

        limiter = PerUserRateLimiter(key="test:2", max_calls=3, period_seconds=60)
        for _ in range(3):
            limiter.allow()
        assert limiter.allow() is False

    def test_period_allows_renewal(self):
        limiter = PerUserRateLimiter(key="test:3", max_calls=2, period_seconds=1)
        assert limiter.allow() is True
        assert limiter.allow() is True
        assert limiter.allow() is False
        time.sleep(1.1)
        assert limiter.allow() is True

    def test_multiple_users_isolated(self):
        a = PerUserRateLimiter(key="user:a", max_calls=1, period_seconds=60)
        b = PerUserRateLimiter(key="user:b", max_calls=1, period_seconds=60)
        assert a.allow() is True
        assert b.allow() is True
        assert a.allow() is False
        assert b.allow() is True  # user b not exhausted
