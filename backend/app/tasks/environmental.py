"""Celery tasks for periodic environmental data collection.

The heavy lifting lives in :class:`~app.services.environmental_service.EnvironmentalService`;
these tasks are thin wrappers so the fetch/persist logic stays reusable and
unit-testable without Celery.

Tasks
-----
``app.tasks.environmental.collect_all_locations``
    Fan-out entry point used by the Beat schedule. Iterates every monitored
    location, collecting weather and air-quality readings for each.
``app.tasks.environmental.collect_location``
    Collects readings for a *single* location -- useful for on-demand or
    fan-out-per-location scheduling.
``app.tasks.environmental.ping``
    Trivial health-check task used to verify worker connectivity.

Each task returns a small JSON-serialisable summary dict so results are easy
to inspect from Flower or the result backend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.logging import request_id_context  # noqa: F401  (re-exported for parity)
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


def collect_for_location(lat: float, lon: float, location_name: str) -> Dict[str, Any]:
    """Fetch weather + air quality for one location and store successful readings.

    Plain (non-task) function so it can be invoked directly in tests and
    one-off scripts, as well as through the Celery tasks below.
    """
    from app.services.environmental_service import EnvironmentalService

    db = _session()
    try:
        service = EnvironmentalService(db)
        summary: Dict[str, Any] = {
            "location": location_name,
            "weather": False,
            "air_quality": False,
        }

        try:
            weather = service.fetch_weather(lat, lon, location_name)
        except Exception as exc:  # provider errors must not kill the batch
            weather = {"error": f"weather fetch failed: {exc}"}
        if "error" not in weather:
            service.save_reading(weather)
            summary["weather"] = True
        else:
            summary["weather_error"] = weather["error"]

        try:
            air = service.fetch_air_quality(lat, lon, location_name)
        except Exception as exc:
            air = {"error": f"air quality fetch failed: {exc}"}
        if "error" not in air:
            service.save_reading(air)
            summary["air_quality"] = True
        else:
            summary["air_quality_error"] = air["error"]

        return summary
    finally:
        db.close()


@celery_app.task(name="app.tasks.environmental.collect_location", bind=True)
def collect_location(
    self, lat: float, lon: float, location_name: str
) -> Dict[str, Any]:
    """Collect readings for a single location (retry on transient failure)."""
    return collect_for_location(lat, lon, location_name)


@celery_app.task(name="app.tasks.environmental.collect_all_locations")
def collect_all_locations(
    locations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Collect readings for every monitored location.

    Scheduled every 15 minutes by Celery Beat. Returns an aggregate summary so
    a single Flower row shows how many locations succeeded and why any failed.
    """
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
