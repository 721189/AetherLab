"""Tests for the provider response cache (expensive-API protection)."""

import asyncio

import pytest

from app.core import provider_cache as pc
from app.services.providers.base import ProviderError
from app.services.providers.openweather_provider import OpenWeatherProvider


def setup_function(_):
    pc.clear_all()


class TestCacheKey:
    def test_nearby_coordinates_share_a_key(self):
        k1 = pc.build_cache_key("openaq", 28.613912, 77.209012)
        k2 = pc.build_cache_key("openaq", 28.613999, 77.209099)
        assert k1 == k2  # rounded to ~110 m

    def test_different_providers_differ(self):
        assert pc.build_cache_key("openaq", 1.0, 2.0) != pc.build_cache_key(
            "openweather", 1.0, 2.0
        )

    def test_time_window_changes_key(self):
        assert pc.build_cache_key("nasa", 1.0, 2.0, "2026-08-24") != (
            pc.build_cache_key("nasa", 1.0, 2.0, "2026-08-25")
        )


class TestMemoryBackend:
    def test_set_then_get_roundtrip(self):
        key = pc.build_cache_key("openaq", 10.0, 20.0)
        pc.set_cached(key, {"aqi": 42}, ttl_seconds=60)
        assert pc.get_cached(key) == {"aqi": 42}

    def test_expired_entry_is_a_miss(self):
        import time

        key = pc.build_cache_key("openaq", 10.0, 20.0)
        pc.set_cached(key, {"aqi": 42}, ttl_seconds=1)
        assert pc.get_cached(key) == {"aqi": 42}  # fresh entry
        time.sleep(1.3)  # let the TTL lapse (works for Redis AND memory backends)
        assert pc.get_cached(key) is None

    def test_miss_returns_none(self):
        assert pc.get_cached("envcache:nothing") is None


class TestDatasetAwareCacheKeys:
    def test_same_coords_different_products_differ(self):
        k2 = pc.build_cache_key("copernicus", 28.61, 77.20,
                                dataset="Sentinel-2 L2A")
        k5 = pc.build_cache_key("copernicus", 28.61, 77.20,
                                dataset="Sentinel-5P L2 NO2")
        assert k2 != k5  # same AOI, completely different datasets

    def test_bands_and_options_participate(self):
        base = pc.build_cache_key("copernicus", 1.0, 2.0, bands=["B04", "B08"])
        other_bands = pc.build_cache_key("copernicus", 1.0, 2.0, bands=["B03"])
        reordered = pc.build_cache_key("copernicus", 1.0, 2.0, bands=["B08", "B04"])
        assert base != other_bands
        assert base == reordered  # band ORDER must not matter

    def test_scene_id_participates(self):
        a = pc.build_cache_key("nasa", 1.0, 2.0, scene_id="POWER-2026-08-24")
        b = pc.build_cache_key("nasa", 1.0, 2.0, scene_id="POWER-2026-08-25")
        assert a != b

    def test_options_participate(self):
        a = pc.build_cache_key("copernicus", 1.0, 2.0, options={"cloud": 20})
        b = pc.build_cache_key("copernicus", 1.0, 2.0, options={"cloud": 80})
        assert a != b


class TestRateLimiterStorageResolution:
    """Production MUST NOT silently degrade to per-process memory storage."""

    def _resolve_with(self, monkeypatch, app_env, redis_url):
        from app.core import rate_limiter as rl

        monkeypatch.setattr(rl.settings, "APP_ENV", app_env)
        monkeypatch.setattr(rl.settings, "REDIS_URL", redis_url)
        return rl._resolve_storage_uri()

    def test_development_falls_back_to_memory(self, monkeypatch):
        result = self._resolve_with(
            monkeypatch, "development",
            "redis://localhost:59999/0",  # nothing listens here
        )
        assert result == "memory://"

    def test_production_fails_closed_when_redis_unreachable(self, monkeypatch):
        with pytest.raises(RuntimeError) as exc_info:
            self._resolve_with(
                monkeypatch, "production", "redis://localhost:59999/0"
            )
        assert "refusing to start" in str(exc_info.value)

    def test_testing_falls_back_to_memory(self, monkeypatch):
        result = self._resolve_with(
            monkeypatch, "testing", "redis://localhost:59999/0"
        )
        assert result == "memory://"


class TestServiceIntegration:
    def _force_memory_backend(self, monkeypatch):
        """Pin the cache to the in-process backend so tests are hermetic even
        when a real Redis is running locally (it persists across runs)."""
        monkeypatch.setattr(pc, "_redis", lambda: None)

    def _service(self, monkeypatch, calls):
        """Service whose provider records each real fetch."""
        import app.services.environmental_service as es
        from app.services.providers.openweather_provider import OpenWeatherProvider

        class CountingProvider(OpenWeatherProvider):
            async def fetch_latest(self, lat, lon, name):
                calls.append((lat, lon))
                return await super().fetch_latest(lat, lon, name)

        svc = es.EnvironmentalService.__new__(es.EnvironmentalService)
        svc.weather_provider = CountingProvider("test-key")
        return svc

    def test_second_identical_request_hits_cache_not_provider(self, monkeypatch):
        self._force_memory_backend(monkeypatch)
        sample = {
            "dt": 1735689600,
            "main": {"temp": 21.5},
            "wind": {},
        }

        async def fake_get_json(url, **kwargs):
            return sample

        monkeypatch.setattr(OpenWeatherProvider, "_get_json", staticmethod(fake_get_json))

        import app.services.environmental_service as es

        calls = []
        svc = self._service(monkeypatch, calls)

        first = asyncio.run(svc.fetch_weather(51.5, -0.12, "London"))
        second = asyncio.run(svc.fetch_weather(51.50005, -0.12004, "London"))

        assert len(calls) == 1  # provider hit exactly once
        assert first["temperature"] == 21.5
        assert second["cached"] is True
        assert second["temperature"] == 21.5

    def test_errors_are_never_cached(self, monkeypatch):
        self._force_memory_backend(monkeypatch)
        from app.services.providers.openweather_provider import OpenWeatherProvider

        async def boom(self, lat, lon, name):
            raise ProviderError("HTTP 503")

        monkeypatch.setattr(OpenWeatherProvider, "fetch_latest", boom)

        import app.services.environmental_service as es

        svc = es.EnvironmentalService.__new__(es.EnvironmentalService)
        svc.weather_provider = OpenWeatherProvider("k")

        first = asyncio.run(svc.fetch_weather(1.0, 2.0, "X"))
        assert "error" in first
        # The failure was not cached — a later success can go through.
        assert pc.get_cached(pc.build_cache_key("openweather", 1.0, 2.0)) is None