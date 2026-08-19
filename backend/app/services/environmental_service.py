import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.environmental_reading import EnvironmentalReading
from app.repositories.environmental_repository import EnvironmentalRepository

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENAQ_URL = "https://api.openaq.org/v2/latest"


class EnvironmentalService:
    """Fetch, transform and persist environmental readings.

    The fetch methods here are kept deliberately thin and *pure* (no DB
    writes); callers decide whether to persist, which makes them trivially
    unit-testable without mocking the database.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = EnvironmentalRepository(db)
        self.openweather_key = settings.OPENWEATHER_API_KEY or os.getenv(
            "OPENWEATHER_API_KEY"
        )
        self.openaq_key = settings.OPENAQ_API_KEY or os.getenv("OPENAQ_API_KEY")

    async def fetch_weather(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> Dict[str, Any]:
        """Fetch current weather from OpenWeather (transformed payload)."""
        if not self.openweather_key:
            return {"error": "OPENWEATHER_API_KEY not set"}

        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.openweather_key,
            "units": "metric",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(OPENWEATHER_URL, params=params)
            data = response.json()

        if response.status_code != 200:
            return {"error": data.get("message", "Weather API error")}

        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_list = data.get("weather") or [{}]

        return {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "humidity": main.get("humidity"),
            "wind_speed": wind.get("speed"),
            "wind_direction": wind.get("deg"),
            "pressure": main.get("pressure"),
            "uv_index": data.get("uv_index"),
            "weather_description": weather_list[0].get("description"),
            "source": "openweather",
        }

    async def fetch_air_quality(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> Dict[str, Any]:
        """Fetch air quality from OpenAQ (transformed payload)."""
        if not self.openaq_key:
            return {"error": "OPENAQ_API_KEY not set"}

        params = {
            "coordinates": f"{lat},{lon}",
            "radius": 1000,
            "limit": 1,
        }
        headers = {"X-API-Key": self.openaq_key}

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(OPENAQ_URL, params=params, headers=headers)
            data = response.json()

        if response.status_code != 200:
            return {"error": data.get("message", "OpenAQ API error")}

        results = data.get("results") or []
        if not results:
            return {"error": "No air quality data available"}

        pollutants: Dict[str, float] = {}
        for reading in (results[0].get("measurements") or []):
            parameter = reading.get("parameter")
            value = reading.get("value")
            if parameter and value is not None:
                pollutants[parameter] = value

        return {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "aqi": self._calculate_aqi(pollutants),
            "pm25": pollutants.get("pm25"),
            "pm10": pollutants.get("pm10"),
            "no2": pollutants.get("no2"),
            "o3": pollutants.get("o3"),
            "co": pollutants.get("co"),
            "so2": pollutants.get("so2"),
            "source": "openaq",
        }

    @staticmethod
    def _calculate_aqi(pollutants: Dict[str, float]) -> Optional[int]:
        """Compute a simplified US AQI from pollutant concentrations.

        The true EPA breakpoints are non-linear; this linear approximation is
        used as a placeholder until a full AQI implementation (e.g. the
        `AQI` python package or EPA tables) is wired in.
        """
        if not pollutants:
            return None

        aqi = 0
        if pollutants.get("pm25"):
            aqi = max(aqi, int(pollutants["pm25"] * 0.5))
        if pollutants.get("pm10"):
            aqi = max(aqi, int(pollutants["pm10"] * 0.3))
        if pollutants.get("no2"):
            aqi = max(aqi, int(pollutants["no2"] * 0.5))

        return min(aqi, 500) if aqi > 0 else None

    def save_reading(self, data: Dict[str, Any]) -> EnvironmentalReading:
        """Persist a single reading (skips error payloads)."""
        if "error" in data:
            return None
        return self.repo.create(data)

    def collect(self, data: Dict[str, Any]) -> Optional[EnvironmentalReading]:
        """Convenience alias combining fetch result + persistence checks."""
        return self.save_reading(data)

    def get_latest_readings(
        self,
        location_name: str,
        limit: int = 10,
    ) -> list[EnvironmentalReading]:
        return self.repo.get_latest_by_location(location_name, limit)

    def get_historical_readings(
        self,
        location_name: str,
        hours: int = 24,
    ) -> list[EnvironmentalReading]:
        cutoff = datetime.now() - timedelta(hours=hours)
        return self.repo.get_by_location_since(location_name, cutoff)
