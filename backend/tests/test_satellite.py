"""Tests for the satellite provider layer (protocol + NASA implementation)."""

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import ProviderError
from app.services.providers.satellite import (
    NASAProvider,
    SatelliteProvider,
    SatelliteScene,
)


class TestProtocol:
    def test_nasa_provider_satisfies_the_satellite_protocol(self):
        assert isinstance(NASAProvider(), SatelliteProvider)

    def test_scene_carries_full_provenance(self):
        scene = SatelliteScene(
            scene_id="S5P-OFFL-NO2-001",
            source="copernicus",
            dataset="Sentinel-5P OFFL/L3__NO2",
            product="L3__NO2",
            processing_level="L3",
            resolution="5.5 km x 7 km",
            acquisition_time=datetime(2026, 8, 25, 10, 32, tzinfo=timezone.utc),
        )
        d = scene.to_dict()
        for field in (
            "scene_id", "source", "dataset", "product",
            "processing_level", "resolution", "acquisition_time",
        ):
            assert field in d


class TestNASAProvider:
    SAMPLE = {
        "properties": {
            "parameter": {
                "T2M": {"20260824": 31.2},
                "RH2M": {"20260824": 64.0},
                "WS2M": {"20260824": -999.0},  # fill value -> masked
            }
        }
    }

    def test_search_returns_scenes(self):
        provider = NASAProvider()
        scenes = asyncio.run(provider.search(28.6, 77.2))
        assert len(scenes) == 1
        assert scenes[0].source == "nasa"

    def test_metadata_roundtrip(self):
        provider = NASAProvider()
        scene = asyncio.run(provider.metadata("POWER-2026-08-24"))
        assert scene.acquisition_time.date() == date(2026, 8, 24)

    def test_metadata_rejects_unknown_scenes(self):
        with pytest.raises(ProviderError):
            asyncio.run(NASAProvider().metadata("S5P-whatever"))

    def test_retrieve_normalises_with_provenance(self):
        provider = NASAProvider()

        async def fake_get_json(url, **kwargs):
            return self.SAMPLE

        with patch.object(NASAProvider, "_get_json", side_effect=fake_get_json):
            observations = asyncio.run(
                provider.retrieve(28.6, 77.2, "POWER-2026-08-24", "Delhi")
            )

        by_var = {o.variable: o for o in observations}
        # Fill values (-999) are dropped.
        assert set(by_var) == {"temperature", "humidity"}
        temp = by_var["temperature"]
        assert isinstance(temp, EnvironmentalObservation)
        assert temp.value == 31.2
        # Provenance is complete and human-presentable.
        assert temp.source == "nasa"
        assert temp.dataset == "POWER T2M"
        assert temp.processing_level == "L3"
        assert temp.resolution
        assert temp.acquisition_time is not None
        assert temp.quality_flags == {"fill_value_masked": True}

    def test_retrieve_raises_when_all_fill_values(self):
        provider = NASAProvider()
        empty = {
            "properties": {
                "parameter": {
                    code: {"20260824": -999.0} for code in provider.PARAMETERS
                }
            }
        }

        async def fake_get_json(url, **kwargs):
            return empty

        with patch.object(NASAProvider, "_get_json", side_effect=fake_get_json):
            with pytest.raises(ProviderError):
                asyncio.run(
                    provider.retrieve(0.0, 0.0, "POWER-2026-08-24")
                )
