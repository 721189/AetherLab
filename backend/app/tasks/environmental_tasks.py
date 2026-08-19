"""Celery background tasks for periodic environmental data collection.

The module is import-safe even when Celery is not installed (it is declared
in requirements.txt but optional at runtime for the HTTP app): the Celery app
is created lazily inside ``get_celery_app``.
"""

from typing import Any, Dict, List, Optional

from app.core.config import settings

# Default set of locations used by the scheduled collection task. In a real
# deployment these would be read from a monitored-locations table.
DEFAULT_LOCATIONS: List[Dict[str, Any]] = [
    {"lat": 28.6139, "lon": 77.2090, "name": "New Delhi"},
    {"lat": 19.0760, "lon": 72.8777, "name": "Mumbai"},
    {"lat": 12.9716, "lon": 77.5946, "name": "Bangalore"},
    {"lat": 22.5726, "lon": 88.3639, "name": "Kolkata"},
    {"lat": 13.0827, "lon": 80.2707, "name": "Chennai"},
]


def _celery_app():
    """Bootstrap (import side-effect free) the Celery application."""
    from celery import Celery

    celery = Celery(
        "aetherlab",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
    )
    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return celery


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def collect_for_location(lat: float, lon: float, location_name: str) -> Dict[str, Any]:
    """Fetch weather + air quality for a location and store any successful
    reading. Returns a small summary dict for observability.

    This is a normal Python function so it can be invoked directly (for tests /
    one-off scripts) as well as via the Celery task below.
    """
    from app.services.environmental_service import EnvironmentalService

    db = _session()
    try:
        service = EnvironmentalService(db)
        stored = {"location": location_name, "weather": False, "air_quality": False}

        fresh_weather = None
        try:
            fresh_weather = service.fetch_weather(lat, lon, location_name)
        except Exception:  # network/provider errors must not kill the batch
            fresh_weather = {"error": "weather fetch failed"}

        if "error" not in fresh_weather:
            service.save_reading(fresh_weather)
            stored["weather"] = True
        else:
            stored["weather_error"] = fresh_weather["error"]

        fresh_aq = None
        try:
            fresh_aq = service.fetch_air_quality(lat, lon, location_name)
        except Exception:
            fresh_aq = {"error": "air quality fetch failed"}

        if "error" not in fresh_aq:
            service.save_reading(fresh_aq)
            stored["air_quality"] = True
        else:
            stored["air_quality_error"] = fresh_aq["error"]

        return stored
    finally:
        db.close()


def scheduled_collection(locations: Optional[List[Dict[str, Any]]] = None) -> None:
    """Synchronously collect data for a list of locations (or the default set).

    Runs in-process; when called through the Celery task it will be executed
    inside a worker (optionally fanning out per-location tasks).
    """
    targets = locations or DEFAULT_LOCATIONS
    for loc in targets:
        collect_for_location(loc["lat"], loc["lon"], loc["name"])


# --- Celery task wrappers -----------------------------------------------
# Defined only when Celery is importable so the HTTP app never hard-depends
# on it. Use ``get_celery_app()`` to register tasks in a worker process.
_task_names = {}


def get_celery_app():
    celery = _celery_app()

    @celery.task(name="environmental.collect_location")
    def collect_location(lat: float, lon: float, location_name: str):
        return collect_for_location(lat, lon, location_name)

    @celery.task(name="environmental.scheduled_collection")
    def scheduled():
        return scheduled_collection()

    _task_names["collect_location"] = collect_location
    _task_names["scheduled_collection"] = scheduled
    return celery


def get_task(name: str):
    """Return a registered task function by name, or None."""
    return _task_names.get(name)
