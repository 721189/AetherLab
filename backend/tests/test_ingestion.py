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
from app.models.environmental_observation import EnvironmentalObservationRecord
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


class TestObservationHashAndIdempotency:
    def _observation(self, variable="pm25", observed_at=None):
        from datetime import datetime, timezone

        return EnvironmentalObservation(
            source="openaq",
            variable=variable,
            value=12.5,
            unit="ug/m3",
            latitude=28.6,
            longitude=77.2,
            location_name="Delhi",
            observed_at=observed_at or datetime(2026, 8, 26, tzinfo=timezone.utc),
            averaging_period="unknown",
            provenance={"provider": "openaq", "site_id": "S-1"},
            quality_flags={"qa": 75},
        )

    def test_observation_hash_is_computed_and_stable(self, db_session):
        repo = EnvironmentalObservationRepository(db_session)
        obs1 = self._observation()
        obs2 = self._observation()
        h1 = repo.compute_observation_hash(obs1)
        h2 = repo.compute_observation_hash(obs2)
        # Same measurement -> same 64-hex hash.
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_when_time_or_variable_differs(self, db_session):
        from datetime import datetime, timezone

        repo = EnvironmentalObservationRepository(db_session)
        base = self._observation(observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc))
        later = self._observation(observed_at=datetime(2026, 8, 27, tzinfo=timezone.utc))
        other_var = self._observation(variable="pm10", observed_at=base.observed_at)
        assert repo.compute_observation_hash(base) != repo.compute_observation_hash(later)
        assert repo.compute_observation_hash(base) != repo.compute_observation_hash(other_var)

    def test_duplicate_observation_is_skipped_idempotently(self, db_session):
        repo = EnvironmentalObservationRepository(db_session)
        obs = self._observation()
        first = repo.create_from(obs)
        assert first is not None
        # Re-fetching the same scene/measurement must NOT create a duplicate.
        count_before = repo.db.query(EnvironmentalObservationRecord).count()
        again = repo.create_from(obs)  # same hash
        assert again is None
        assert repo.db.query(EnvironmentalObservationRecord).count() == count_before

    def test_create_many_is_idempotent_across_retries(self, db_session):
        repo = EnvironmentalObservationRepository(db_session)
        batch = [self._observation(), self._observation("pm10")]
        first = repo.create_many(batch)
        assert len(first) == 2
        # Retry the same batch: no new rows, no exception.
        retry = repo.create_many(batch)
        assert retry == []
        assert repo.db.query(EnvironmentalObservationRecord).count() == 2

    def test_atomic_batch_rolls_back_on_failure(self, db_session, monkeypatch):
        """If ANY row in the batch fails, the ENTIRE batch is rolled back."""
        repo = EnvironmentalObservationRepository(db_session)
        batch = [self._observation(), self._observation("pm10")]

        # Force a failure on the second insert by making commit raise.
        original_commit = db_session.commit

        def boom():
            raise RuntimeError("simulated commit failure")

        count_before = repo.db.query(EnvironmentalObservationRecord).count()
        monkeypatch.setattr(db_session, "commit", boom)
        try:
            repo.create_many(batch)
        except RuntimeError as exc:
            assert "simulated" in str(exc)
        finally:
            db_session.commit = original_commit

        # No partial write survived.
        assert repo.db.query(EnvironmentalObservationRecord).count() == count_before

    def test_timestamps_normalised_to_utc(self, db_session):
        from datetime import datetime, timedelta, timezone

        repo = EnvironmentalObservationRepository(db_session)
        obs = self._observation()
        obs.observed_at = datetime(2026, 8, 26, 12, 0, 0)  # naive -> assumed UTC
        obs.retrieved_at = datetime(
            2026, 8, 26, 17, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )  # IST -> should convert to UTC
        record = repo.create_from(obs)
        # Naive observed_at is treated as UTC and unchanged.
        assert record.observed_at.hour == 12
        # 17:00 IST == 11:30 UTC: the stored value must reflect UTC even though
        # SQLite strips the tz offset on read-back (PostgreSQL preserves it
        # via DateTime(timezone=True)).
        assert record.retrieved_at.hour == 11 and record.retrieved_at.minute == 30

    def test_provenance_and_quality_flags_roundtrip_as_native_dict(self, db_session):
        from datetime import datetime, timezone

        repo = EnvironmentalObservationRepository(db_session)
        obs = self._observation(observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc))
        record = repo.create_from(obs)
        # Fresh session read-back to verify JSON round-trip.
        db_session.expire_all()
        re_read = (
            repo.db.query(EnvironmentalObservationRecord)
            .filter_by(id=record.id)
            .first()
        )
        assert isinstance(re_read.provenance, dict)
        assert isinstance(re_read.quality_flags, dict)
        assert re_read.provenance["site_id"] == "S-1"
        assert re_read.quality_flags["qa"] == 75


class _FakePointProvider:
    """Returns a canned observation list regardless of call."""

    def __init__(self, sample):
        self.sample = sample

    async def fetch_latest(self, lat, lon, location_name):
        return self.sample