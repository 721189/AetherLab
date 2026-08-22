"""Tests for the Celery app + environmental collection tasks.

Celery runs with ``task_always_eager = True`` in these tests, so tasks execute
synchronously in-process and no Redis broker/backend is required. Provider
calls are monkeypatched, keeping the suite offline and deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks import environmental as env_tasks
from app.tasks.celery_app import ENVIRONMENTAL_COLLECTION_INTERVAL_SECONDS, celery_app


@pytest.fixture
def eager_celery(monkeypatch):
    """Run tasks synchronously and reset state around each test."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield celery_app
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture
def fake_db(monkeypatch):
    """Replace the real DB session with an in-test recording double."""
    created: list = []

    class FakeRepo:
        def create(self, data):
            created.append(data)
            return SimpleNamespace(**data)

    class FakeService:
        def __init__(self, db):
            self.db = db

        def fetch_weather(self, lat, lon, name):
            return {"location_name": name, "temperature": 21.5, "source": "openweather"}

        def fetch_air_quality(self, lat, lon, name):
            return {"location_name": name, "aqi": 42, "source": "openaq"}

        def save_reading(self, data):
            if "error" in data:
                return None
            created.append(data)

        @property
        def repo(self):
            return FakeRepo()

    # Patch the symbol imported *inside* the task module's function body.
    # The real session is closed in a ``finally`` block, so the double needs
    # a matching no-op ``close()``.
    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(
        env_tasks, "_session", lambda: FakeSession(), raising=True
    )
    import app.services.environmental_service as es

    monkeypatch.setattr(es, "EnvironmentalService", FakeService)
    return created


def test_celery_app_configuration() -> None:
    assert celery_app.main == "aetherlab"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True


def test_beat_schedule_runs_the_collection_task_every_15_minutes() -> None:
    entry = celery_app.conf.beat_schedule["fetch-environmental-data-every-15-min"]
    assert entry["task"] == "app.tasks.environmental.collect_all_locations"
    assert entry["schedule"] == ENVIRONMENTAL_COLLECTION_INTERVAL_SECONDS == 900.0


def test_all_expected_tasks_are_registered() -> None:
    expected = {
        "app.tasks.environmental.collect_all_locations",
        "app.tasks.environmental.collect_location",
        "app.tasks.environmental.ping",
    }
    assert expected.issubset(celery_app.tasks)


def test_broker_and_backend_point_at_redis() -> None:
    from app.core.config import settings

    assert celery_app.conf.broker_url == settings.REDIS_URL
    assert celery_app.conf.result_backend == settings.REDIS_URL


def test_ping_task_returns_pong(eager_celery) -> None:
    from app.tasks.environmental import ping

    assert ping.apply().get() == "pong"


def test_collect_location_stores_weather_and_air_quality(
    eager_celery, fake_db
) -> None:
    from app.tasks.environmental import collect_location

    result = collect_location.apply(args=(51.5, -0.12, "London")).get()
    assert result["location"] == "London"
    assert result["weather"] is True
    assert result["air_quality"] is True
    assert len(fake_db) == 2


def test_collect_all_locations_aggregates_every_target(
    eager_celery, fake_db, monkeypatch
) -> None:
    from app.tasks.environmental import collect_all_locations

    custom = [
        {"lat": 1.0, "lon": 2.0, "name": "Alpha"},
        {"lat": 3.0, "lon": 4.0, "name": "Beta"},
    ]
    summary = collect_all_locations.apply(args=(custom,)).get()
    assert summary["locations"] == 2
    assert summary["succeeded"] == 2
    assert [r["location"] for r in summary["results"]] == ["Alpha", "Beta"]


def test_collect_all_locations_defaults_to_the_monitored_set(
    eager_celery, fake_db
) -> None:
    from app.tasks.environmental import DEFAULT_LOCATIONS, collect_all_locations

    summary = collect_all_locations.apply().get()
    assert summary["locations"] == len(DEFAULT_LOCATIONS)


def test_provider_failure_does_not_abort_the_batch(eager_celery, monkeypatch) -> None:
    """A network error for one source must not lose the other source."""
    import app.services.environmental_service as es

    recorded: list = []

    class FlakyService:
        def __init__(self, db):
            self.db = db

        def fetch_weather(self, lat, lon, name):
            raise RuntimeError("connection reset")

        def fetch_air_quality(self, lat, lon, name):
            return {"location_name": name, "aqi": 10, "source": "openaq"}

        def save_reading(self, data):
            if "error" not in data:
                recorded.append(data)

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(env_tasks, "_session", FakeSession)
    monkeypatch.setattr(es, "EnvironmentalService", FlakyService)

    from app.tasks.environmental import collect_location

    result = collect_location.apply(args=(0.0, 0.0, "Nowhere")).get()
    assert result["weather"] is False
    assert "weather_error" in result
    assert result["air_quality"] is True
    assert len(recorded) == 1  # only the air-quality reading persisted
