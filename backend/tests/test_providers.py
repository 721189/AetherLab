"""Tests for the provider adapters + canonical observation schema.

Provider JSON shapes are simulated offline; the adapters must normalise them
into EnvironmentalObservation records — raw payloads never leak through.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import ProviderError
from app.services.providers.openaq_provider import OpenAQProvider
from app.services.providers.openweather_provider import OpenWeatherProvider


class TestOpenWeatherAdapter:
    SAMPLE = {
        "dt": 1735689600,
        "main": {"temp": 21.5, "feels_like": 20.1, "humidity": 60, "pressure": 1013},
        "wind": {"speed": 3.4, "deg": 210},
        "uv_index": 4.0,
    }

    def test_normalises_into_canonical_observations(self):
        provider = OpenWeatherProvider("test-key")
        with patch.object(
            OpenWeatherProvider, "_get_json", new=AsyncMock(return_value=self.SAMPLE)
        ):
            observations = asyncio.run(
                provider.fetch_latest(51.5, -0.12, "London")
            )
        assert observations
        for obs in observations:
            assert isinstance(obs, EnvironmentalObservation)
            assert obs.source == "openweather"
            assert obs.location_name == "London"

    def test_missing_key_raises_provider_error(self):
        provider = OpenWeatherProvider("")
        with pytest.raises(ProviderError):
            asyncio.run(provider.fetch_latest(0.0, 0.0, "X"))

    def test_to_reading_payload_flattens(self):
        provider = OpenWeatherProvider("k")
        with patch.object(
            OpenWeatherProvider, "_get_json", new=AsyncMock(return_value=self.SAMPLE)
        ):
            observations = asyncio.run(provider.fetch_latest(1.0, 2.0, "T"))
        payload = OpenWeatherProvider.to_reading_payload(1.0, 2.0, "T", observations)
        values = {o.variable: o.value for o in observations}
        assert payload["temperature"] == values["temperature"]
        assert payload["source"] == "openweather"


class TestOpenAQV3Adapter:
    LOCATIONS = {
        "results": [{"id": 42, "datetime": {"utc": "2026-01-01T00:00:00Z"}}]
    }
    DETAIL = {
        "sensors": [
            {"id": 1, "parameter": {"name": "pm25", "units": "ug/m3"}},
            {"id": 2, "parameter": {"name": "no2", "units": "ug/m3"}},
        ]
    }
    LATEST = {"results": [{"sensorsId": 1, "value": 40}, {"sensorsId": 2, "value": 40}]}

    def _patch_chain(self):
        responses = [self.LOCATIONS, self.DETAIL, self.LATEST]

        async def fake_get_json(url, **kwargs):
            return responses.pop(0)

        return patch.object(OpenAQProvider, "_get_json", side_effect=fake_get_json)

    def test_v3_flow_normalises_canonical_observations(self):
        provider = OpenAQProvider("test-key")
        with self._patch_chain():
            observations = asyncio.run(
                provider.fetch_latest(28.6139, 77.2090, "New Delhi")
            )
        by_var = {o.variable: o for o in observations}
        assert by_var["pm25"].value == 40.0
        assert by_var["no2"].value == 40.0
        for obs in observations:
            assert isinstance(obs, EnvironmentalObservation)
            assert obs.source == "openaq"
            assert obs.unit == "ug/m3"

    def test_aqi_computed_with_epa_methodology(self):
        from app.core.aqi import calculate_overall_aqi

        provider = OpenAQProvider("test-key")
        with self._patch_chain():
            observations = asyncio.run(
                provider.fetch_latest(28.6139, 77.2090, "New Delhi")
            )
        payload = OpenAQProvider.to_reading_payload(
            28.6139, 77.2090, "New Delhi", observations
        )
        expected = calculate_overall_aqi(
            {o.variable: o.value for o in observations},
            units={o.variable: o.unit for o in observations},
            averaging_periods={o.variable: o.averaging_period
                               for o in observations},
        )
        assert payload["aqi"] == expected["aqi"]
        # Instantaneous OpenAQ readings are NOT EPA-averaged windows — the
        # AQI must be labelled indicative, never standard-derived.
        assert expected["methodology_status"] == "non_standard_averaging"
        assert payload["aqi_methodology"]["methodology_status"] == (
            "non_standard_averaging"
        )
        # pm25 of 40 sits in the Unhealthy-for-Sensitive-Groups band.
        assert payload["aqi"] > 100

    def test_no_nearby_location_raises_provider_error(self):
        provider = OpenAQProvider("test-key")

        async def empty(url, **kwargs):
            return {"results": []}

        with patch.object(OpenAQProvider, "_get_json", side_effect=empty):
            with pytest.raises(ProviderError):
                asyncio.run(provider.fetch_latest(0.0, 0.0, "Nowhere"))

    def test_service_maps_provider_errors_to_error_dicts(self, db_session):
        """The service boundary converts ProviderError into error payloads."""
        import app.services.environmental_service as es

        svc = es.EnvironmentalService.__new__(es.EnvironmentalService)
        svc.air_quality_provider = OpenAQProvider("k")

        async def boom(lat, lon, name):
            raise ProviderError("HTTP 503 from api.openaq.org")

        with patch.object(OpenAQProvider, "fetch_latest", side_effect=boom):
            result = asyncio.run(svc.fetch_air_quality(1.0, 2.0, "X"))
        assert result == {"error": "HTTP 503 from api.openaq.org"}
