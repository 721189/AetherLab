"""Tests for the CDSE / Sentinel-5P NO2 provider."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.providers.base import ProviderError
from app.services.providers.copernicus_provider import (
    CopernicusProvider,
    PRODUCT_TYPE,
    PROCESSING_LEVEL,
)

SAMPLE_ITEM = {
    "Id": "a1b2c3",
    "Name": "S5P_OFFL_L2__NO2____20260824T101203",
    "ContentDate": {"Start": "2026-08-24T10:12:03Z"},
    "Online": True,
    "Footprint": "POLYGON((...))",
}


class TestSearch:
    def _provider(self):
        return CopernicusProvider(catalogue_url="http://cdse.test")

    def test_search_returns_provenanced_scenes(self):
        provider = self._provider()

        async def fake_get_json(url, params):
            assert params["productType"] == PRODUCT_TYPE
            assert "bbox" in params and "startDate" in params
            return {"value": [SAMPLE_ITEM]}

        with patch.object(provider, "_get_json", side_effect=fake_get_json):
            scenes = asyncio.run(provider.search(28.61, 77.21))

        assert len(scenes) == 1
        scene = scenes[0]
        assert scene.source == "copernicus"
        assert scene.scene_id == "a1b2c3"
        assert "Sentinel-5P TROPOMI" in scene.dataset
        assert scene.processing_level == "L2"

    def test_catalogue_unreachable_raises_provider_error(self):
        provider = self._provider()

        async def boom(url, params):
            raise ProviderError("CDSE catalogue unreachable: timeout")

        with patch.object(provider, "_get_json", side_effect=boom):
            with pytest.raises(ProviderError):
                asyncio.run(provider.search(0.0, 0.0))


class TestRetrieveHonesty:
    """retrieve() must NEVER fabricate values when extraction isn't possible."""

    def test_without_credentials_raises_actionable_error(self):
        provider = CopernicusProvider(username="", password="")
        with pytest.raises(ProviderError) as exc_info:
            asyncio.run(provider.retrieve(28.6, 77.2, "a1b2c3"))
        # The error names exactly what is missing.
        assert "COPERNICUS_USERNAME" in str(exc_info.value)

    def test_with_credentials_but_no_quota_also_refuses_to_fabricate(self):
        from datetime import datetime, timezone

        from app.services.providers.satellite import SatelliteScene

        provider = CopernicusProvider(username="u", password="p")
        scene = SatelliteScene(
            scene_id="a1b2c3", source="copernicus", dataset="Sentinel-5P",
            product=PRODUCT_TYPE, processing_level=PROCESSING_LEVEL,
            resolution="7x3.5km",
            acquisition_time=datetime(2026, 8, 24, tzinfo=timezone.utc),
        )
        with patch.object(
            provider, "_get_token", new=AsyncMock(return_value="token")
        ), patch.object(provider, "metadata", new=AsyncMock(return_value=scene)):
            with pytest.raises(ProviderError) as exc_info:
                asyncio.run(provider.retrieve(28.6, 77.2, "a1b2c3"))
        assert "openEO" in str(exc_info.value)


class TestProtocolConformance:
    def test_copernicus_satisfies_satellite_protocol(self):
        from app.services.providers.satellite import SatelliteProvider

        assert isinstance(CopernicusProvider(), SatelliteProvider)
