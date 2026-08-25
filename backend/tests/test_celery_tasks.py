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
    """Replace the real DB session with an in-test recording double.

    The fake service mirrors the REAL service's execution model: its fetch
    methods are ``async def`` returning plain dicts. This is exactly what lets
    ``test_collect_location_executes_environmental_fetches`` catch the classic
    sync/async mixing bug — if the task ever treated coroutines as results,
    these assertions would fail.
    """
    created: list = []
    calls = {"weather": 0, "air_quality": 0}

    class FakeRepo:
        def create(self, data):
            created.append(data)
            return SimpleNamespace(**data)

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def fetch_weather(self, lat, lon, name):
            calls["weather"] += 1
            return {"location_name": name, "temperature": 21.5, "source": "openweather"}

        async def fetch_air_quality(self, lat, lon, name):
            calls["air_quality"] += 1
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
    return created, calls



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

    created, _ = fake_db
    result = collect_location.apply(args=(51.5, -0.12, "London")).get()
    assert result["location"] == "London"
    assert result["weather"] is True
    assert result["air_quality"] is True
    assert len(created) == 2


def test_collect_location_executes_environmental_fetches(
    eager_celery, fake_db
) -> None:
    """Regression guard for the sync/async execution-model mismatch.

    The environmental service is async; the Celery task is sync. If the task
    ever mixed them incorrectly (calling the coroutine without awaiting it),
    the results here would be coroutine objects / failures instead of the
    actual fetched dictionaries asserted below.
    """
    import inspect

    from app.services.environmental_service import EnvironmentalService

    created, calls = fake_db
    from app.tasks.environmental import collect_location

    result = collect_location.apply(args=(28.6139, 77.2090, "New Delhi")).get()

    # Both providers were actually executed.
    assert calls["weather"] == 1
    assert calls["air_quality"] == 1
    assert result.successful() if hasattr(result, "successful") else True
    # The task summary reflects REAL dictionaries, not coroutine objects.
    assert isinstance(result, dict)
    assert result == {
        "location": "New Delhi",
        "weather": True,
        "air_quality": True,
    }
    # The persisted payloads are the actual fetched dicts.
    persisted = {d["source"]: d for d in created}
    assert persisted["openweather"]["temperature"] == 21.5
    assert persisted["openaq"]["aqi"] == 42
    # Sanity: nothing anywhere returned a bare coroutine.
    for data in created:
        assert not inspect.iscoroutine(data)


def test_collect_all_locations_fans_out_per_location(
    eager_celery, fake_db, monkeypatch
) -> None:
    """Beat dispatches ONE independent task per location (no serial for-loop)."""
    from app.tasks.environmental import collect_all_locations

    custom = [
        {"lat": 1.0, "lon": 2.0, "name": "Alpha"},
        {"lat": 3.0, "lon": 4.0, "name": "Beta"},
    ]
    monkeypatch.setattr(
        __import__("app.tasks.environmental", fromlist=["x"]),
        "discover_locations",
        lambda: custom,
    )

    created, _ = fake_db
    summary = collect_all_locations.apply().get()

    # Dispatch summary returned to Beat/Flower...
    assert summary["dispatched"] == 2
    assert summary["locations"] == ["Alpha", "Beta"]
    # ...and in eager mode each fanned-out task actually ran and persisted.
    names = {d["location_name"] for d in created}
    assert {"Alpha", "Beta"}.issubset(names)


def test_collect_all_locations_discovers_from_the_database(
    eager_celery, fake_db, monkeypatch
) -> None:
    from app.tasks import environmental as env_mod

    calls = []

    def fake_discover():
        calls.append(1)
        return [{"lat": 10.0, "lon": 20.0, "name": "DbCity"}]

    monkeypatch.setattr(env_mod, "discover_locations", fake_discover)
    summary = collect_all = env_mod.collect_all_locations.apply().get()
    assert calls  # discovery was consulted, not the hardcoded defaults
    assert collect_all["locations"] == ["DbCity"]


def test_collect_all_locations_defaults_to_the_monitored_set(
    eager_celery, fake_db
) -> None:
    """Empty/unavailable monitored_locations table -> platform defaults."""
    from app.tasks.environmental import DEFAULT_LOCATIONS, collect_all_locations

    summary = collect_all_locations.apply().get()
    assert summary["locations"] == [loc["name"] for loc in DEFAULT_LOCATIONS]


def test_provider_failure_does_not_abort_the_batch(eager_celery, monkeypatch) -> None:
    """A network error for one source must not lose the other source."""
    import asyncio

    import app.services.environmental_service as es

    recorded: list = []

    class FlakyService:
        def __init__(self, db):
            self.db = db

        async def fetch_weather(self, lat, lon, name):
            raise RuntimeError("connection reset")

        async def fetch_air_quality(self, lat, lon, name):
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


def test_task_boundary_uses_a_single_event_loop_per_task(eager_celery, fake_db) -> None:
    """The async boundary is one asyncio.run per task, never per request."""
    import ast
    import inspect

    import app.tasks.environmental as mod

    source = inspect.getsource(mod.collect_for_location)
    tree = ast.parse(source)
    loop_creations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert len(loop_creations) == 1  # exactly one event loop per task call
    # ...and it lives in the SYNC wrapper, not inside the async orchestration.
    async_src = inspect.getsource(mod.collect_for_location_async)
    assert "asyncio.run" not in async_src
