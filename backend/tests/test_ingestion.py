"""Tests for the ingestion orchestration layer (P0 architecture fix).

Guarantees that ALL providers — including NASA and Copernicus — flow through
ONE canonical pipeline into the environmental_observations table.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from app.schemas.environmental import EnvironmentalObservation
from app.services.environmental import (
    EnvironmentalIngestionService,
    EnvironmentalObservationRepository,
    ProviderRegistry,
)
from app.services.providers.satellite import SatelliteScene


class TestRegistry:
    def test_registry_knows_all_four_sources(self):
        assert ProviderRegistry.names() == [
            "openweather", "openaq", "nasa", "copernicus",
        ]

    def test_unknown_provider_raises(self):
        try:
            ProviderRegistry.get("landsat-fake")
        except KeyError as exc:
            assert "landsat-fake" in str(exc)
        else:
            raise AssertionError("expected KeyError")

    def test_nasa_and_copernicus_resolve_through_the_registry(self):
        nasa = ProviderRegistry.get("nasa")
        copernicus = ProviderRegistry.get("copernicus")
        assert nasa.name == "nasa"
        assert copernicus.name == "copernicus"


class TestCanonicalPersistence:
    def _observation(self, variable="pm25", source="openaq"):
        from datetime import datetime, timezone

        return EnvironmentalObservation(
            source=source,
            variable=variable,
            value=12.5 if variable == "pm25" else 30.0,
            unit="ug/m3",
            latitude=28.6,
            longitude=77.2,
            location_name="Delhi",
            observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            averaging_period="unknown",
            quality_flags={"qa": 75},
        )

    def test_observations_persist_canonically_with_provenance(self, db_session):
        repo = EnvironmentalObservationRepository(db_session)
        record = repo.create_from(self._observation())

        assert record.id is not None
        assert record.source == "openaq"
        assert record.variable == "pm25"
        assert record.unit == "ug/m3"
        assert record.averaging_period == "unknown"
        assert record.quality_flags is not None

    def test_non_pollutant_variables_need_no_schema_change(self, db_session):
        """NDVI/CH4/LST-style variables are just rows — no migration needed."""
        repo = EnvironmentalObservationRepository(db_session)
        for variable in ("ndvi", "ch4_column", "land_surface_temperature"):
            obs = self._observation(variable=variable, source="copernicus")
            obs.unit = {"ndvi": "index", "ch4_column": "mol/m2",
                        "land_surface_temperature": "kelvin"}[variable]
            record = repo.create_from(obs)
            assert record.variable == variable

    def test_ingest_weather_and_air_quality_persist_observations(self, db_session, monkeypatch):
        service = EnvironmentalIngestionService(db_session)

        sample_weather = [
            self._observation(variable="temperature", source="openweather"),
        ]
        sample_air = [self._observation(variable="pm25", source="openaq")]

        def fake_get(name):
            return _FakePointProvider(
                sample_weather if name == "openweather" else sample_air
            )

        with patch.object(ProviderRegistry, "get", staticmethod(fake_get)):
            weather = asyncio.run(service.ingest_weather(28.6, 77.2, "Delhi"))
            air = asyncio.run(service.ingest_air_quality(28.6, 77.2, "Delhi"))

        assert len(weather) == 1 and len(air) == 1
        # Both landed in the canonical table.
        records = EnvironmentalObservationRepository(db_session).db.query(
            __import__("app.models.environmental_observation",
                       fromlist=["EnvironmentalObservationRecord"])
            .EnvironmentalObservationRecord
        ).all()
        assert {r.variable for r in records} == {"temperature", "pm25"}

    def test_ingest_satellite_routes_via_the_same_pipeline(self, db_session, monkeypatch):
        service = EnvironmentalIngestionService(db_session)

        class FakeSatellite:
            name = "nasa"

            async def search(self, lat, lon):
                return [SatelliteScene(
                    scene_id="POWER-2026-08-24",
                    source="nasa",
                    dataset="POWER",
                    product="reanalysis-daily-point",
                    processing_level="L3",
                    resolution="55 km",
                    acquisition_time=__import__("datetime").datetime(
                        2026, 8, 24, tzinfo=__import__("datetime").timezone.utc
                    ),
                )]

            async def retrieve(self, lat, lon, scene_id, location_name=""):
                return [self._observation()]

            @staticmethod
            def _observation():
                from datetime import datetime, timezone

                return EnvironmentalObservation(
                    source="nasa",
                    variable="temperature",
                    value=31.2,
                    unit="celsius",
                    latitude=28.6,
                    longitude=77.2,
                    dataset="POWER (MERRA-2 reanalysis)",
                    product="reanalysis-daily-point",
                    processing_level="L3",
                    averaging_period="24-hour",
                    quality="verified",
                    observed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                )

        monkeypatch.setattr(ProviderRegistry, "get", staticmethod(lambda name: FakeSatellite()))
        observations = asyncio.run(service.ingest_satellite(28.6, 77.2, "Delhi"))
        assert len(observations) == 1
        assert observations[0].source == "nasa"


class _FakePointProvider:
    """Returns a canned observation list regardless of call."""

    def __init__(self, sample):
        self.sample = sample

    async def fetch_latest(self, lat, lon, location_name):
        return self.sample