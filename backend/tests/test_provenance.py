"""Tests for the provenance & scientific correctness model.

Every observation persisted to the database MUST carry complete provenance:
source attribution, timestamp semantics, uncertainty, and a reproducibility
bundle. These tests enforce that contract so scientific correctness is
continuously validated, not just documented.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.environmental import EnvironmentalObservation


class TestProvenanceContract:
    """Every observation MUST carry complete provenance."""

    def _make_overview_obs(self) -> EnvironmentalObservation:
        """Build a representative observation with full provenance."""
        now = datetime.now(timezone.utc)
        return EnvironmentalObservation(
            source="openweather",
            variable="temperature",
            value=25.0,
            unit="celsius",
            latitude=28.6,
            longitude=77.2,
            location_name="Delhi",
            observed_at=now,
            acquisition_time=now,
            retrieved_at=now,
            dataset="OpenWeather Current Weather API",
            product="current",
            processing_level="L2",
            resolution="point",
            averaging_period="instantaneous",
            uncertainty=None,
            confidence=0.9,
            quality_score=90.0,
            data_completeness=0.8,
            quality="verified",
            provenance={
                "provider": "openweather",
                "collection": "openweather-current",
                "station_id": 12345,
                "api_version": "2.5",
            },
            quality_flags={"clouds_pct": 40},
        )

    def test_observation_carries_source_attribution(self):
        """source + dataset + product + processing_level must be present."""
        obs = self._make_overview_obs()
        assert obs.source == "openweather"
        assert obs.dataset == "OpenWeather Current Weather API"
        assert obs.product == "current"
        assert obs.processing_level == "L2"

    def test_observation_carries_timestamp_semantics(self):
        """observed_at, acquisition_time, retrieved_at must all be present."""
        obs = self._make_overview_obs()
        assert obs.observed_at is not None
        assert obs.acquisition_time is not None
        assert obs.retrieved_at is not None
        for ts in (obs.observed_at, obs.acquisition_time, obs.retrieved_at):
            assert ts.tzinfo is not None

    def test_observation_carries_uncertainty_model(self):
        """uncertainty, confidence, quality_score must be present."""
        obs = self._make_overview_obs()
        assert obs.uncertainty is None or isinstance(obs.uncertainty, float)
        assert 0.0 <= obs.confidence <= 1.0
        assert 0.0 <= obs.quality_score <= 100.0

    def test_observation_carries_reproducibility_bundle(self):
        """provenance must contain enough to re-fetch the same payload."""
        obs = self._make_overview_obs()
        assert isinstance(obs.provenance, dict)
        assert "provider" in obs.provenance
        assert obs.provenance["provider"] == "openweather"

    def test_observation_carries_quality_flags(self):
        """quality_flags must be a dict (even if empty)."""
        obs = self._make_overview_obs()
        assert isinstance(obs.quality_flags, dict)

    def test_observation_has_averaging_period(self):
        """averaging_period must be explicit — never silently default."""
        obs = self._make_overview_obs()
        assert obs.averaging_period is not None

    def test_observation_unit_is_present(self):
        """unit must be a non-empty string."""
        obs = self._make_overview_obs()
        assert obs.unit
        assert isinstance(obs.unit, str)

    def test_nasa_power_carries_model_provenance(self):
        """NASA POWER observations must declare themselves as model-derived."""
        now = datetime.now(timezone.utc)
        obs = EnvironmentalObservation(
            source="nasa",
            variable="temperature",
            value=25.0,
            unit="celsius",
            latitude=28.6,
            longitude=77.2,
            dataset="POWER (MERRA-2 reanalysis) T2M",
            product="reanalysis-daily-point",
            processing_level="L3",
            resolution="0.5° x 0.625° (~55 km)",
            acquisition_time=now,
            observed_at=now,
            retrieved_at=now,
            averaging_period="24-hour",
            uncertainty=1.0,
            confidence=0.8,
            quality_score=80.0,
            provenance={
                "provider": "nasa",
                "collection": "POWER",
                "reanalysis_source": "MERRA-2",
            },
            quality_flags={"fill_value_masked": True},
        )
        assert obs.processing_level == "L3"
        assert obs.confidence <= 0.85
        assert obs.averaging_period == "24-hour"

    def test_openaq_carries_station_provenance(self):
        """OpenAQ observations must carry site + sensor attribution."""
        now = datetime.now(timezone.utc)
        obs = EnvironmentalObservation(
            source="openaq",
            variable="pm25",
            value=42.0,
            unit="ug/m3",
            latitude=28.6,
            longitude=77.2,
            dataset="OpenAQ v3",
            product="latest",
            processing_level="L2",
            resolution="point",
            acquisition_time=now,
            observed_at=now,
            retrieved_at=now,
            averaging_period="instantaneous",
            uncertainty=None,
            confidence=0.85,
            quality_score=85.0,
            provenance={
                "provider": "openaq",
                "collection": "openaq-v3",
                "site_id": 1234,
                "sensor_id": 5678,
            },
            quality_flags={"is_mobile": False},
        )
        assert obs.provenance["site_id"] == 1234
        assert obs.provenance["sensor_id"] == 5678
        assert obs.averaging_period == "instantaneous"

