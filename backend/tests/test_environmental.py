"""Tests for the environmental data ingestion feature.

These tests exercise the persistence + querying layer and the API endpoints
using the in-memory SQLite database shared with the app's dependency override.
External HTTP calls to OpenWeather/OpenAQ are avoided by testing the pure
payload transforms directly.
"""
import pytest
from sqlalchemy.orm import sessionmaker

from app.services.environmental_service import EnvironmentalService


@pytest.fixture
def db_session(db_engine):
    """Session bound to the same in-memory engine the app uses, so data
    inserted here is visible to requests made via the TestClient."""
    session_factory = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False
    )
    session = session_factory()
    yield session
    session.close()


def seed_readings(db_session, location_name="Delhi", count=3):
    svc = EnvironmentalService(db_session)
    for i in range(count):
        svc.save_reading(
            {
                "location_name": location_name,
                "lat": 28.61,
                "lon": 77.21,
                "temperature": 30.0 + i,
                "humidity": 60 + i,
                "aqi": 100 + i,
                "source": "openweather" if i % 2 == 0 else "openaq",
            }
        )
    return db_session


class TestRepositoryPersistence:
    def test_create_filters_unknown_keys(self, db_session):
        svc = EnvironmentalService(db_session)
        reading = svc.save_reading(
            {
                "location_name": "Mumbai",
                "lat": 19.0,
                "lon": 72.8,
                "temperature": 28.0,
                "source": "openweather",
                "bogus_extra_key": "should be dropped",
            }
        )
        assert reading is not None
        assert reading.location_name == "Mumbai"
        assert reading.temperature == 28.0
        assert not hasattr(reading, "bogus_extra_key")

    def test_save_reading_skips_error_payloads(self, db_session):
        svc = EnvironmentalService(db_session)
        assert svc.save_reading({"error": "OPENWEATHER_API_KEY not set"}) is None

    def test_get_latest_and_historical(self, db_session):
        seed_readings(db_session)
        svc = EnvironmentalService(db_session)

        latest = svc.get_latest_readings("Delhi", limit=10)
        assert len(latest) == 3
        # Newest-first ordering.
        assert latest[0].aqi == max(r.aqi for r in latest)

        historical = svc.get_historical_readings("Delhi", hours=24)
        assert len(historical) == 3

    def test_geofence(self, db_session):
        seed_readings(db_session)
        svc = EnvironmentalService(db_session)

        nearby = svc.repo.get_by_geofence(28.61, 77.21, 5)
        assert len(nearby) == 3
        assert svc.repo.get_by_geofence(0.0, 0.0, 5) == []


class TestAQICalculation:
    def test_simplified_aqi(self):
        calc = EnvironmentalService._calculate_aqi
        assert calc({"pm25": 80}) == 40
        assert calc({"pm10": 100}) == 30
        assert calc({}) is None
        # Clamped at 500.
        assert calc({"pm25": 5000}) == 500
        # Takes the max across pollutants.
        assert calc({"pm25": 100, "no2": 120}) == 60


class TestWeatherNoKey:
    def test_fetch_weather_without_key_returns_error(self):
        svc = EnvironmentalService.__new__(EnvironmentalService)
        svc.openweather_key = ""
        # Call the synchronous wrapper by invoking the coroutine directly via
        # the event loop pytest provides through anyio.
        import asyncio

        result = asyncio.run(svc.fetch_weather(1.0, 2.0, "X"))
        assert result == {"error": "OPENWEATHER_API_KEY not set"}


class TestEndpoints:
    def test_latest_no_data_returns_empty_list(self, client, db_session):
        resp = client.get("/api/v1/environmental/latest", params={"location_name": "Delhi"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_latest_with_data(self, client, db_session):
        seed_readings(db_session)
        resp = client.get(
            "/api/v1/environmental/latest", params={"location_name": "Delhi"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        # First row is the most recent.
        assert body[0]["aqi"] == max(r["aqi"] for r in body)
        assert body[0]["source"] in {"openweather", "openaq"}

    def test_historical_with_data(self, client, db_session):
        seed_readings(db_session)
        resp = client.get(
            "/api/v1/environmental/historical",
            params={"location_name": "Delhi", "hours": 24},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_reading_by_id(self, client, db_session):
        seed_readings(db_session)
        # Grab a known id from the DB.
        svc = EnvironmentalService(db_session)
        reading = svc.get_latest_readings("Delhi", 1)[0]
        resp = client.get(f"/api/v1/environmental/readings/{reading.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == reading.id
        assert "temperature" in resp.json()

    def test_reading_not_found(self, client, db_session):
        resp = client.get("/api/v1/environmental/readings/99999")
        assert resp.status_code == 404

    def test_latest_missing_location_query_is_validated(self, client):
        resp = client.get("/api/v1/environmental/latest")
        assert resp.status_code == 422
