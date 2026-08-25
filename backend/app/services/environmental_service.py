import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.environmental_reading import EnvironmentalReading
from app.repositories.environmental_repository import EnvironmentalRepository
from app.services.providers.openaq_provider import OpenAQProvider
from app.services.providers.base import ProviderError
from app.services.providers.openweather_provider import OpenWeatherProvider


class EnvironmentalService:
    """Fetch, transform and persist environmental readings.

    All provider-specific logic lives in :mod:`app.services.providers`
    adapters; this service orchestrates them and persists canonical results.
    Fetch methods are async and *pure* (no DB writes); callers decide whether
    to persist, which keeps them trivially unit-testable.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = EnvironmentalRepository(db)
        self.weather_provider = OpenWeatherProvider(
            settings.OPENWEATHER_API_KEY or os.getenv("OPENWEATHER_API_KEY", "")
        )
        self.air_quality_provider = OpenAQProvider(
            settings.OPENAQ_API_KEY or os.getenv("OPENAQ_API_KEY", "")
        )

    @property
    def openweather_key(self) -> str:
        return self.weather_provider.api_key

    @property
    def openaq_key(self) -> str:
        return self.air_quality_provider.api_key

    async def fetch_weather(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> Dict[str, Any]:
        """Fetch current weather from OpenWeather via its adapter."""
        try:
            observations = await self.weather_provider.fetch_latest(
                lat, lon, location_name
            )
        except ProviderError as exc:
            return {"error": str(exc)}
        return OpenWeatherProvider.to_reading_payload(
            lat, lon, location_name, observations
        )

    async def fetch_air_quality(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> Dict[str, Any]:
        """Fetch air quality from OpenAQ v3 via its adapter."""
        try:
            observations = await self.air_quality_provider.fetch_latest(
                lat, lon, location_name
            )
        except ProviderError as exc:
            return {"error": str(exc)}
        payload = OpenAQProvider.to_reading_payload(
            lat, lon, location_name, observations
        )
        if payload is None:
            return {"error": "No air quality data available"}
        return payload

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

