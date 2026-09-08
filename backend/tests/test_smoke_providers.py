"""Live external-provider contract tests (smoke tier).

These hit the REAL OpenWeather / OpenAQ / NASA endpoints and consume API
quota, so they only run when explicitly opted in:

    RUN_PROVIDER_SMOKE=1 OPENWEATHER_API_KEY=... OPENAQ_API_KEY=... \\
        pytest -m smoke

They exist to catch provider-side contract drift (schema changes, retired
endpoints) that mocks cannot see.
"""

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("RUN_PROVIDER_SMOKE") != "1",
        reason="Opt-in live tests: set RUN_PROVIDER_SMOKE=1 (consumes API quota)",
    ),
]


@pytest.mark.skipif(
    not (os.environ.get("OPENAQ_API_KEY")),
    reason="OPENAQ_API_KEY not configured",
)
class TestOpenAQLive:
    def test_v3_contract_still_matches_adapter(self):
        import asyncio

        from app.services.providers.openaq_provider import OpenAQProvider

        observations = asyncio.run(
            OpenAQProvider(os.environ["OPENAQ_API_KEY"]).fetch_latest(
                28.6139, 77.2090, "New Delhi"
            )
        )
        assert observations, "Adapter returned nothing for a known monitored area"
        for obs in observations:
            assert obs.source == "openaq"
            assert obs.variable and obs.unit
            assert obs.observed_at is not None


@pytest.mark.skipif(
    not (os.environ.get("OPENWEATHER_API_KEY")),
    reason="OPENWEATHER_API_KEY not configured",
)
class TestOpenWeatherLive:
    def test_current_weather_contract(self):
        import asyncio

        from app.services.providers.openweather_provider import OpenWeatherProvider

        observations = asyncio.run(
            OpenWeatherProvider(os.environ["OPENWEATHER_API_KEY"]).fetch_latest(
                51.5074, -0.1278, "London"
            )
        )
        variables = {o.variable for o in observations}
        assert "temperature" in variables


class TestNASALive:
    """NASA POWER needs no API key; safe-ish to exercise when opted in."""

    def test_power_endpoint_reachable_and_schema_stable(self):
        import asyncio

        from app.services.providers.satellite import NASAProvider

        observations = asyncio.run(
            NASAProvider().retrieve(28.6139, 77.2090, "POWER-2026-08-20", "Delhi")
        )
        assert observations
        temp = next(o for o in observations if o.variable == "temperature")
        assert -50 < temp.value < 60  # sanity band for surface air temperature


class TestCopernicusLive:
    """Copernicus CDSE catalogue search is public (no credentials required).

    Only catalogue search/metadata are exercised here — value extraction from
    NetCDF products requires CDSE openEO/Processing credentials and is
    deliberately NOT attempted (it would silently fail or fabricate).
    """

    def test_catalogue_search_reachable_and_schema_stable(self):
        import asyncio
        from datetime import date, timedelta

        from app.services.providers.copernicus_provider import CopernicusProvider

        scenes = asyncio.run(
            CopernicusProvider().search(
                lat=28.6139,
                lon=77.2090,
                start=date.today() - timedelta(days=7),
                end=date.today(),
                max_records=3,
            )
        )
        # The catalogue should be reachable and return scene entries (can be
        # empty for extreme windows, but a recent week over Delhi should
        # normally have TROPOMI passes).
        assert isinstance(scenes, list)
        for scene in scenes:
            assert scene.scene_id
            assert scene.source == "copernicus"


class TestSentinel2Live:
    """Sentinel-2 CDSE OData catalogue discovery is public (no credentials).

    Only scene discovery is exercised — NDVI extraction requires local B04/B08
    band files and is deliberately NOT attempted (the provider refuses to
    fabricate NDVI).
    """

    def test_discover_scenes_reachable_and_schema_stable(self):
        import asyncio
        from datetime import date, timedelta

        from app.services.providers.sentinel2_provider import Sentinel2Provider

        scenes = asyncio.run(
            Sentinel2Provider().discover_scenes(
                bbox=[77.0, 28.5, 77.5, 29.0],  # Delhi area
                start=date.today() - timedelta(days=7),
                end=date.today(),
                max_cloud=50,
                max_results=3,
            )
        )
        assert isinstance(scenes, list)
        for scene in scenes:
            assert scene.scene_id
            assert scene.source == "sentinel2"


@pytest.mark.skipif(
    not (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="No LLM API key configured (set OPENROUTER_API_KEY or OPENAI_API_KEY)",
)
class TestLLMLive:
    """Live LLM provider roundtrip (opt-in; consumes tokens).

    Verifies the configured provider can be reached and returns a non-empty
    grounded response — catches model deprecation / auth / base-URL drift.
    """

    def test_openrouter_roundtrip(self):
        import os

        from app.ai.providers.openrouter import OpenRouterProvider

        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not configured")

        provider = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
        reply = provider.generate_response(
            [{"role": "user", "content": "Reply with exactly one word: OK"}],
            max_tokens=8,
        )
        assert reply and isinstance(reply, str)

    def test_openai_roundtrip(self):
        import os

        from app.ai.providers.openai import OpenAIProvider

        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not configured")

        provider = OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        reply = provider.generate_response(
            [{"role": "user", "content": "Reply with exactly one word: OK"}],
            max_tokens=8,
        )
        assert reply and isinstance(reply, str)
