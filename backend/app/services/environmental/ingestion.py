"""Environmental ingestion orchestration — the single canonical path.

    ProviderRegistry (openweather | openaq | nasa | copernicus)
        |
    EnvironmentalIngestionService
        .ingest_weather()      -> canonical observations -> DB
        .ingest_air_quality()  -> canonical observations -> DB (+ AQI record)
        .ingest_satellite(src) -> canonical observations -> DB

Every provider's output is normalised into EnvironmentalObservation records
and persisted into ``environmental_observations`` — no provider-specific JSON
ever reaches the database. Celery tasks call this service; the legacy
flattened EnvironmentalReading snapshot is derived only for API compatibility.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.environmental_observation import EnvironmentalObservationRecord
from app.schemas.environmental import EnvironmentalObservation


class EnvironmentalObservationRepository:
    """Persistence for canonical observations."""

    def __init__(self, db: Session):
        self.db = db

    def create_from(self, obs: EnvironmentalObservation) -> EnvironmentalObservationRecord:
        record = EnvironmentalObservationRecord(
            source=obs.source,
            dataset=obs.dataset,
            product=obs.product,
            processing_level=obs.processing_level,
            variable=obs.variable,
            value=obs.value,
            unit=obs.unit,
            latitude=obs.latitude,
            longitude=obs.longitude,
            location_name=obs.location_name,
            observed_at=obs.observed_at,
            acquisition_time=obs.acquisition_time,
            retrieved_at=obs.retrieved_at,
            averaging_period=obs.averaging_period,
            resolution=obs.resolution,
            quality=obs.quality,
            quality_flags=json.dumps(obs.quality_flags) if obs.quality_flags else None,
            provenance=json.dumps(obs.provenance) if obs.provenance else None,
            uncertainty=obs.uncertainty,
            confidence=obs.confidence,
            quality_score=obs.quality_score,
            data_completeness=obs.data_completeness,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def create_many(
        self, observations: List[EnvironmentalObservation]
    ) -> List[EnvironmentalObservationRecord]:
        return [self.create_from(o) for o in observations]


class ProviderRegistry:
    """Single lookup of every environmental data provider by name."""

    _instances: dict = {}

    @classmethod
    def get(cls, name: str):
        name = name.lower()
        if name in cls._instances:
            return cls._instances[name]

        import os

        from app.core.config import settings

        if name == "openweather":
            from app.services.providers.openweather_provider import OpenWeatherProvider

            instance = OpenWeatherProvider(
                settings.OPENWEATHER_API_KEY or os.getenv("OPENWEATHER_API_KEY", "")
            )
        elif name == "openaq":
            from app.services.providers.openaq_provider import OpenAQProvider

            instance = OpenAQProvider(
                settings.OPENAQ_API_KEY or os.getenv("OPENAQ_API_KEY", "")
            )
        elif name == "nasa":
            from app.services.providers.satellite import NASAProvider

            instance = NASAProvider()
        elif name == "copernicus":
            from app.services.providers.copernicus_provider import CopernicusProvider

            instance = CopernicusProvider(
                username=settings.COPERNICUS_USERNAME,
                password=settings.COPERNICUS_PASSWORD,
            )
        else:
            raise KeyError(f"Unknown environmental provider {name!r}")

        cls._instances[name] = instance
        return instance

    @classmethod
    def names(cls) -> List[str]:
        return ["openweather", "openaq", "nasa", "copernicus"]


class EnvironmentalIngestionService:
    """Orchestrates every provider into one canonical persistence path."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = EnvironmentalObservationRepository(db)

    # ------------------------------------------------------------------
    # Point-observation sources
    # ------------------------------------------------------------------
    async def ingest_weather(
        self, lat: float, lon: float, location_name: str
    ) -> List[EnvironmentalObservation]:
        provider = ProviderRegistry.get("openweather")
        observations = await provider.fetch_latest(lat, lon, location_name)
        return self.repo.create_many(observations)

    async def ingest_air_quality(
        self, lat: float, lon: float, location_name: str
    ) -> List[EnvironmentalObservation]:
        provider = ProviderRegistry.get("openaq")
        observations = await provider.fetch_latest(lat, lon, location_name)
        return self.repo.create_many(observations)

    # ------------------------------------------------------------------
    # Satellite sources (catalogue-driven protocol)
    # ------------------------------------------------------------------
    async def ingest_satellite(
        self,
        lat: float,
        lon: float,
        location_name: str = "",
        source: str = "nasa",
    ) -> List[EnvironmentalObservation]:
        provider = ProviderRegistry.get(source)
        scenes = await provider.search(lat, lon)
        if not scenes:
            raise RuntimeError(f"No scenes found for {source} at ({lat}, {lon})")

        collected: List[EnvironmentalObservation] = []
        errors: List[str] = []
        for scene in scenes:
            try:
                collected.extend(
                    await provider.retrieve(lat, lon, scene.scene_id, location_name)
                )
            except Exception as exc:
                errors.append(f"{scene.scene_id}: {exc}")
        if errors and not collected:
            raise RuntimeError(
                f"All satellite retrievals failed: {'; '.join(errors)}"
            )
        return self.repo.create_many(collected)

    # ------------------------------------------------------------------
    # Legacy snapshot derivation (API compatibility only)
    # ------------------------------------------------------------------
    @staticmethod
    def derive_reading_payload(
        lat: float,
        lon: float,
        location_name: str,
        weather_observations: List[EnvironmentalObservation],
        air_quality_observations: List[EnvironmentalObservation],
    ):
        """Derive the flattened legacy reading dict from canonical observations."""
        from app.core.aqi import calculate_overall_aqi
        from app.services.providers.openaq_provider import CANONICAL_UNITS

        payload: Dict[str, Any] = {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "source": "openweather",
        }
        for obs in weather_observations:
            if obs.variable in (
                "temperature", "feels_like", "humidity", "pressure",
                "wind_speed", "wind_direction",
            ):
                payload[obs.variable] = obs.value

        pollutants = {
            o.variable: o.value
            for o in air_quality_observations
            if o.variable in CANONICAL_UNITS and o.value is not None
        }
        if pollutants:
            aqi_record = calculate_overall_aqi(
                pollutants,
                units={o.variable: o.unit for o in air_quality_observations
                       if o.variable in CANONICAL_UNITS},
                averaging_periods={o.variable: o.averaging_period
                                   for o in air_quality_observations},
            )
            payload.update(
                {
                    "source": "openaq",
                    "aqi": aqi_record["aqi"],
                    "aqi_methodology": aqi_record,
                    **{v: pollutants.get(v) for v in CANONICAL_UNITS},
                }
            )
            return payload
        return payload if weather_observations else None
