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
