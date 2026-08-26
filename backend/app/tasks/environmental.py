"""Celery tasks for periodic environmental data collection.

Execution-model note
--------------------
The environmental service is **async** (httpx.AsyncClient under the hood),
while Celery workers are synchronous. Mixing the two incorrectly — e.g.
calling an async method and treating the returned coroutine as a result, or
spinning a fresh event loop per API request — is a classic bug. The correct
boundary used here is:

    sync Celery task
        -> ONE asyncio.run(...) per task
            -> async orchestration function
                -> async EnvironmentalService (provider adapters)

Each task returns a small JSON-serialisable summary dict so results are easy
to inspect from Flower or the result backend.

Tasks
-----
``app.tasks.environmental.collect_all_locations``
    Fan-out entry point used by the Beat schedule.
``app.tasks.environmental.collect_location``
    Collects readings for a *single* location.
``app.tasks.environmental.ping``
    Trivial health-check task used to verify worker connectivity.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.tasks.celery_app import celery_app

# Default set of locations used by the scheduled collection task. In a real
# deployment these would be read from a monitored-locations table.
DEFAULT_LOCATIONS: List[Dict[str, Any]] = [
    {"lat": 28.6139, "lon": 77.2090, "name": "New Delhi"},
    {"lat": 19.0760, "lon": 72.8777, "name": "Mumbai"},
    {"lat": 12.9716, "lon": 77.5946, "name": "Bangalore"},
    {"lat": 22.5726, "lon": 88.3639, "name": "Kolkata"},
    {"lat": 13.0827, "lon": 80.2707, "name": "Chennai"},
]


def _session():
    """Open a short-lived DB session (imported lazily to avoid app import)."""
    from app.db.session import SessionLocal

    return SessionLocal()


async def collect_for_location_async(
    lat: float,
    lon: float,
    location_name: str,
) -> Dict[str, Any]:
    """Async orchestration for one location — canonical ingestion path.

    All providers flow through EnvironmentalIngestionService, which persists
    canonical EnvironmentalObservation records; a flattened legacy snapshot
    is derived afterwards purely for API compatibility.
    """
    from app.services.environmental import EnvironmentalIngestionService

    db = _session()
    try:
        ingestion = EnvironmentalIngestionService(db)
        summary: Dict[str, Any] = {
            "location": location_name,
            "weather": False,
            "air_quality": False,
        }

        async def _safe(coro, label):
            try:
                return await coro
            except Exception as exc:  # provider errors must not kill the batch
                return {"error": f"{label} failed: {exc}"}

        weather_obs, air_obs = await asyncio.gather(
            _safe(ingestion.ingest_weather(lat, lon, location_name), "weather"),
            _safe(ingestion.ingest_air_quality(lat, lon, location_name), "air quality"),
        )

        if isinstance(weather_obs, list) and weather_obs:
            summary["weather"] = True
        else:
            summary["weather_error"] = weather_obs.get("error", "no data")
        if isinstance(air_obs, list) and air_obs:
            summary["air_quality"] = True
        else:
            summary["air_quality_error"] = air_obs.get("error", "no data")

        # Derived legacy snapshot for API compatibility (best-effort).
        if summary["weather"] or summary["air_quality"]:
            try:
                payload = EnvironmentalIngestionService.derive_reading_payload(
                    lat,
                    lon,
                    location_name,
                    weather_obs if isinstance(weather_obs, list) else [],
                    air_obs if isinstance(air_obs, list) else [],
                )
                if payload:
                    from app.services.environmental_service import EnvironmentalService

                    EnvironmentalService(db).save_reading(payload)
            except Exception:
                pass  # canonical data is already persisted; snapshot is optional

        return summary
    finally:
        db.close()


def collect_for_location(lat: float, lon: float, location_name: str) -> Dict[str, Any]:
    """Synchronous entry point wrapping the async orchestration.

    Creates exactly ONE event loop per call (i.e. one per Celery task
    execution) — never one per individual API request.
    """
    return asyncio.run(collect_for_location_async(lat, lon, location_name))


@celery_app.task(name="app.tasks.environmental.collect_location", bind=True)
def collect_location(
    self, lat: float, lon: float, location_name: str
) -> Dict[str, Any]:
    """Collect readings for a single location."""
    return collect_for_location(lat, lon, location_name)


@celery_app.task(name="app.tasks.environmental.collect_satellite")
def collect_satellite(
    lat: float,
    lon: float,
    location_name: str = "",
    source: str = "nasa",
) -> Dict[str, Any]:
    """Ingest satellite observations for one location via the canonical path.

    Dispatchable per-source so NASA POWER meteorology and Copernicus
    Sentinel-5P catalogue products run as independent queue messages.
    """
    import asyncio

    from app.services.environmental import EnvironmentalIngestionService

    db = _session()
    try:
        ingestion = EnvironmentalIngestionService(db)
        try:
            observations = asyncio.run(
                ingestion.ingest_satellite(lat, lon, location_name, source=source)
            )
        except Exception as exc:
            return {
                "location": location_name or f"{lat},{lon}",
                "source": source,
                "ok": False,
                "error": str(exc),
            }
        return {
            "location": location_name or f"{lat},{lon}",
            "source": source,
            "ok": True,
            "observations": len(observations),
        }
    finally:
        db.close()


def discover_locations() -> List[Dict[str, Any]]:
    """Read enabled monitored locations from the database.

    Falls back to :data:`DEFAULT_LOCATIONS` when the table is empty OR the
    database is unreachable — a Beat tick must never crash because of a
    transient DB blip; the platform defaults are always safe to collect.
    """
    import logging

    logger = logging.getLogger(__name__)
    from app.repositories.monitored_location_repository import (
        MonitoredLocationRepository,
    )

    db = _session()
    try:
        rows = MonitoredLocationRepository(db).get_enabled()
        if not rows:
            return list(DEFAULT_LOCATIONS)
        return [
            {
                "lat": r.latitude,
                "lon": r.longitude,
                "name": r.name,
                "location_id": r.id,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Could not read monitored locations (%s); using defaults", exc)
        return list(DEFAULT_LOCATIONS)
    finally:
        db.close()


@celery_app.task(name="app.tasks.environmental.collect_all_locations")
def collect_all_locations() -> Dict[str, Any]:
    """Discover enabled locations and FAN OUT one task per location.

    Architecture:

        Beat -> collect_all_locations -> discover_locations()
              -> celery.group(collect_location.s(loc) for loc ...)

    Each location runs as an independent task on the queue, so one failing
    or slow location can never hold up the rest of the batch — the worker
    pool processes them in parallel and failures are isolated per message.
    Returns a dispatch summary; per-location outcomes land in Flower.
    """
    from celery import group

    targets = discover_locations()
    if not targets:
        return {"dispatched": 0, "locations": []}

    signatures = [
        collect_location.signature(
            kwargs={
                "lat": t["lat"],
                "lon": t["lon"],
                "location_name": t["name"],
            }
        )
        for t in targets
    ]
    group(signatures).apply_async()

    return {
        "dispatched": len(signatures),
        "locations": [t["name"] for t in targets],
    }


@celery_app.task(name="app.tasks.environmental.ping")
def ping() -> str:
    """Liveness probe for the worker (used by tests / ops checks)."""
    return "pong"
