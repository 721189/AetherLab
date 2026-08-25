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
    """Async orchestration for one location: fetch both sources, persist.

    The DB session stays synchronous (the project uses standard SQLAlchemy);
    only the HTTP fetches are awaited, concurrently via asyncio.gather so a
    slow weather response never delays the air-quality request.
    """
    from app.services.environmental_service import EnvironmentalService

    db = _session()
    try:
        service = EnvironmentalService(db)

        async def _safe(coro, label):
            try:
                return await coro
            except Exception as exc:  # provider errors must not kill the batch
                return {"error": f"{label} fetch failed: {exc}"}

        weather, air = await asyncio.gather(
            _safe(
                service.fetch_weather(lat, lon, location_name), "weather"
            ),
            _safe(
                service.fetch_air_quality(lat, lon, location_name), "air quality"
            ),
        )

        summary: Dict[str, Any] = {
            "location": location_name,
            "weather": "error" not in weather,
            "air_quality": "error" not in air,
        }
        if summary["weather"]:
            service.save_reading(weather)
        else:
            summary["weather_error"] = weather["error"]
        if summary["air_quality"]:
            service.save_reading(air)
        else:
            summary["air_quality_error"] = air["error"]
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


@celery_app.task(name="app.tasks.environmental.collect_all_locations")
def collect_all_locations(
    locations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Collect readings for every monitored location (Beat: every 15 min)."""
    targets = locations or DEFAULT_LOCATIONS
    results = [
        collect_for_location(loc["lat"], loc["lon"], loc["name"]) for loc in targets
    ]
    return {
        "locations": len(results),
        "succeeded": sum(
            1 for r in results if r.get("weather") or r.get("air_quality")
        ),
        "results": results,
    }


@celery_app.task(name="app.tasks.environmental.ping")
def ping() -> str:
    """Liveness probe for the worker (used by tests / ops checks)."""
    return "pong"
