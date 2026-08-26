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

import hashlib
import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.environmental_observation import EnvironmentalObservationRecord
from app.schemas.environmental import EnvironmentalObservation


class EnvironmentalObservationRepository:
    """Persistence for canonical observations.

    Persistence is **batch-atomic** and **idempotent**:

    - ``create_many`` inserts the whole batch in a single transaction and
      rolls back completely if anything fails — no partial batch is ever
      committed.
    - Every observation is tagged with ``observation_hash`` (SHA-256 of the
      canonical dedup key: source + dataset + product + scene_id + variable +
      location + observed_at). Pre-existing rows with the same hash are
      skipped, so a Celery retry or re-fetching the same satellite scene can
      never produce a duplicate observation.
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def compute_observation_hash(obs: EnvironmentalObservation) -> str:
        """SHA-256 over the canonical dedup key for one observation.

        The key intentionally excludes the numeric value and retrieval time:
        the same measurement (same source scene, variable, place and time)
        must hash identically across retries even if the provider payload
        differs slightly.
        """
        scene_id = None
        if isinstance(obs.provenance, dict):
            scene_id = obs.provenance.get("scene_id")

        canonical = json.dumps(
            {
                "source": obs.source,
                "dataset": obs.dataset,
                "product": obs.product,
                "scene_id": scene_id,
                "variable": obs.variable,
                "location": (round(obs.latitude, 5), round(obs.longitude, 5)),
                "observed_at": (
                    EnvironmentalObservationRepository._utc(obs.observed_at).isoformat()
                    if obs.observed_at else None
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc(dt: Any) -> Any:
        """Normalise a timestamp to timezone-aware UTC.

        Naive datetimes are assumed to be UTC and are tagged as such;
        aware datetimes are converted to UTC. This guarantees everything
        stored in ``environmental_observations`` is canonical UTC regardless
        of what a provider returns.
        """
        if dt is None:
            return None
        from datetime import timezone

        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _to_record(
        self, obs: EnvironmentalObservation
    ) -> EnvironmentalObservationRecord:
        return EnvironmentalObservationRecord(
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
            observed_at=self._utc(obs.observed_at),
            acquisition_time=self._utc(obs.acquisition_time),
            retrieved_at=self._utc(obs.retrieved_at),
            averaging_period=obs.averaging_period,
            resolution=obs.resolution,
            quality=obs.quality,
            # JSONB columns accept native dicts on PostgreSQL (and serialise
            # them as JSON on SQLite) — do NOT json.dumps here.
            quality_flags=obs.quality_flags if obs.quality_flags else None,
            provenance=obs.provenance if obs.provenance else None,
            uncertainty=obs.uncertainty,
            confidence=obs.confidence,
            quality_score=obs.quality_score,
            data_completeness=obs.data_completeness,
            observation_hash=self.compute_observation_hash(obs),
        )

    def create_from(
        self, obs: EnvironmentalObservation
    ) -> EnvironmentalObservationRecord | None:
        rec = self._to_record(obs)
        # Idempotency pre-check: skip rows that already exist.
        if self._hash_exists(rec.observation_hash):
            return None
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def _hash_exists(self, observation_hash: str) -> bool:
        return (
            self.db.query(EnvironmentalObservationRecord)
            .filter(
                EnvironmentalObservationRecord.observation_hash == observation_hash
            )
            .first()
            is not None
        )

    def create_many(
        self, observations: List[EnvironmentalObservation]
    ) -> List[EnvironmentalObservationRecord]:
        """Insert a batch atomically; idempotently skip existing observations.

        New rows for this batch are added to the session and committed exactly
        once. If anything fails, the entire batch is rolled back (no partial
        writes). Already-persisted hashes are excluded first, so a retried
        batch never inserts duplicates and never fails on a UNIQUE violation.
        """
        records: List[EnvironmentalObservationRecord] = []
        for obs in observations:
            rec = self._to_record(obs)
            if self._hash_exists(rec.observation_hash):
                continue  # already collected — idempotent skip
            self.db.add(rec)
            records.append(rec)

        if not records:
            return []

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()  # atomic: no partial batch
            raise
        return records


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
