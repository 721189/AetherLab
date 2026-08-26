"""Tests for the Celery app + environmental collection tasks.

Celery runs with ``task_always_eager = True`` in these tests, so tasks execute
synchronously in-process and no Redis broker/backend is required. Provider
calls are monkeypatched, keeping the suite offline and deterministic.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone

import pytest

from app.schemas.environmental import EnvironmentalObservation
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
    """Replace the real DB + ingestion service with recording doubles.

    The fakes mirror the REAL pipeline's execution model: ingestion methods
    are ``async def`` returning lists of canonical EnvironmentalObservation
    records. This is what lets ``test_collect_location_executes_environmental_fetches``
    catch the classic sync/async mixing bug -- if the task ever treated
    coroutines as results, these assertions would fail.
    """
    created: list = []
    calls = {"weather": 0, "air_quality": 0}

    def _obs(variable, value, unit, source, name):
        return EnvironmentalObservation(
            source=source,
            variable=variable,
            value=value,
            unit=unit,
            latitude=0.0,
            longitude=0.0,
            location_name=name,
            observed_at=datetime.now(timezone.utc),
            averaging_period="unknown",
        )

    class FakeIngestion:
        """Records every canonical observation it 'persists'."""

        def __init__(self, db):
            self.db = db

        async def ingest_weather(self, lat, lon, name):
            calls["weather"] += 1
            observations = [
                _obs("temperature", 21.5, "celsius", "openweather", name)
            ]
            created.extend(observations)
            return observations

        async def ingest_air_quality(self, lat, lon, name):
            calls["air_quality"] += 1
            observations = [_obs("pm25", 12.5, "ug/m3", "openaq", name)]
            created.extend(observations)
            return observations

        async def ingest_satellite(self, lat, lon, location_name="", source="nasa"):
            # Delegates to the registry exactly like the real implementation,
            # so tests can patch ProviderRegistry independently.
            provider = env_pkg.ProviderRegistry.get(source)
            scenes = await provider.search(lat, lon)
            observations = []
            for scene in scenes:
                scene_id = scene if isinstance(scene, str) else scene.scene_id
                observations.extend(
                    await provider.retrieve(lat, lon, scene_id, location_name)
                )
            created.extend(observations)
            return observations

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(
        env_tasks, "_session", lambda: FakeSession(), raising=True
    )
    import app.services.environmental as env_pkg

    monkeypatch.setattr(env_pkg, "EnvironmentalIngestionService", FakeIngestion)
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
        "app.tasks.environmental.collect_satellite",
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
    """Regression guard for the sync/async execution-model mismatch."""
    created, calls = fake_db
    from app.tasks.environmental import collect_location

    result = collect_location.apply(args=(28.6139, 77.2090, "New Delhi")).get()

    assert calls["weather"] == 1
    assert calls["air_quality"] == 1
    # Real results -- never coroutine objects.
    assert isinstance(result, dict)
    assert result == {
        "location": "New Delhi",
        "weather": True,
        "air_quality": True,
    }
    persisted = {o.variable: o for o in created}
    assert persisted["temperature"].value == 21.5
    assert persisted["pm25"].value == 12.5
    for data in created:
        assert not inspect.iscoroutine(data)


def test_collect_location_uses_the_canonical_ingestion_path(
    eager_celery, fake_db
) -> None:
    """Canonical EnvironmentalObservations, not legacy flattened dicts."""
    created, _ = fake_db
    from app.tasks.environmental import collect_location

    collect_location.apply(args=(10.0, 20.0, "X")).get()
    for observation in created:
        assert isinstance(observation, EnvironmentalObservation)
        assert observation.source in {"openweather", "openaq"}


def test_collect_satellite_task_persists_canonical_observations(
    eager_celery, fake_db, monkeypatch
) -> None:
    from app.tasks.environmental import collect_satellite

    class FakeSatellite:
        name = "nasa"

        async def search(self, lat, lon):
            return ["scene-1"]

        async def retrieve(self, lat, lon, scene_id, location_name=""):
            return [
                EnvironmentalObservation(
                    source="nasa",
                    variable="temperature",
                    value=31.2,
                    unit="celsius",
                    latitude=lat,
                    longitude=lon,
                    dataset="POWER (MERRA-2 reanalysis)",
                    product="reanalysis-daily-point",
                    processing_level="L3",
                    averaging_period="24-hour",
                    quality="verified",
                )
            ]

    import app.services.environmental as env_pkg

    monkeypatch.setattr(
        env_pkg.ProviderRegistry, "get", staticmethod(lambda n: FakeSatellite())
    )

    result = collect_satellite.apply(args=(28.6, 77.2, "Delhi")).get()
    assert result == {
        "location": "Delhi",
        "source": "nasa",
        "ok": True,
        "observations": 1,
    }


def test_collect_satellite_reports_failure_without_raising(eager_celery, monkeypatch):
    from app.tasks.environmental import collect_satellite

    class ExplodingProvider:
        name = "copernicus"

        async def search(self, lat, lon):
            raise RuntimeError("CDSE unreachable")

    import app.services.environmental as env_pkg

    monkeypatch.setattr(
        env_pkg.ProviderRegistry, "get", staticmethod(lambda n: ExplodingProvider())
    )

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(env_tasks, "_session", lambda: FakeSession())
    result = collect_satellite.apply(args=(0.0, 0.0)).get()
    assert result["ok"] is False
    assert "CDSE unreachable" in result["error"]


def test_collect_all_locations_fans_out_per_location(
    eager_celery, fake_db, monkeypatch
) -> None:
    """Beat dispatches ONE independent task per location (no serial for-loop)."""
    from app.tasks.environmental import collect_all_locations

    custom = [
        {"lat": 1.0, "lon": 2.0, "name": "Alpha"},
        {"lat": 3.0, "lon": 4.0, "name": "Beta"},
    ]
    monkeypatch.setattr(env_tasks, "discover_locations", lambda: custom)

    created, _ = fake_db
    summary = collect_all_locations.apply().get()

    assert summary["dispatched"] == 2
    assert summary["locations"] == ["Alpha", "Beta"]
    names = {o.location_name for o in created}
    assert {"Alpha", "Beta"} <= names


def test_collect_all_locations_discovers_from_the_database(
    eager_celery, fake_db, monkeypatch
) -> None:
    discovery_calls = []

    def fake_discover():
        discovery_calls.append(1)
        return [{"lat": 10.0, "lon": 20.0, "name": "DbCity"}]

    monkeypatch.setattr(env_tasks, "discover_locations", fake_discover)
    from app.tasks.environmental import collect_all_locations

    summary = collect_all_locations.apply().get()
    assert discovery_calls  # DB discovery consulted, not hardcoded defaults
    assert summary["locations"] == ["DbCity"]


def test_collect_all_locations_defaults_when_table_empty(
    eager_celery, fake_db
) -> None:
    """Empty/unavailable monitored_locations table -> platform defaults."""
    from app.tasks.environmental import DEFAULT_LOCATIONS, collect_all_locations

    summary = collect_all_locations.apply().get()
    assert summary["locations"] == [loc["name"] for loc in DEFAULT_LOCATIONS]


def test_provider_failure_does_not_abort_the_batch(eager_celery, monkeypatch) -> None:
    """A network error for one source must not lose the other source."""
    recorded: list = []

    class FlakyIngestion:
        def __init__(self, db):
            self.db = db

        async def ingest_weather(self, lat, lon, name):
            raise RuntimeError("connection reset")

        async def ingest_air_quality(self, lat, lon, name):
            obs = EnvironmentalObservation(
                source="openaq", variable="pm25", value=10.0, unit="ug/m3",
                latitude=lat, longitude=lon, location_name=name,
                observed_at=datetime.now(timezone.utc),
            )
            recorded.append(obs)
            return [obs]

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(env_tasks, "_session", lambda: FakeSession())
    import app.services.environmental as env_pkg

    monkeypatch.setattr(env_pkg, "EnvironmentalIngestionService", FlakyIngestion)

    from app.tasks.environmental import collect_location

    result = collect_location.apply(args=(0.0, 0.0, "Nowhere")).get()
    assert result["weather"] is False
    assert "weather_error" in result
    assert result["air_quality"] is True
    assert len(recorded) == 1  # only the air-quality reading persisted


def test_task_boundary_uses_a_single_event_loop_per_task(eager_celery) -> None:
    """The async boundary is one asyncio.run per task, never per request."""
    tree = ast.parse(inspect.getsource(env_tasks.collect_for_location))
    loop_creations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert len(loop_creations) == 1
    # ...and it lives in the SYNC wrapper, not inside the async orchestration.
    assert "asyncio.run" not in inspect.getsource(
        env_tasks.collect_for_location_async
    )
