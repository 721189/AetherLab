"""Environmental data provider adapters."""

from app.services.providers.base import EnvironmentalProvider, ProviderError
from app.services.providers.copernicus_provider import CopernicusProvider
from app.services.providers.openaq_provider import OpenAQProvider
from app.services.providers.openweather_provider import OpenWeatherProvider
from app.services.providers.satellite import (
    NASAProvider,
    SatelliteProvider,
    SatelliteScene,
)

__all__ = [
    "EnvironmentalProvider",
    "ProviderError",
    "CopernicusProvider",
    "OpenAQProvider",
    "OpenWeatherProvider",
    "SatelliteProvider",
    "SatelliteScene",
    "NASAProvider",
]
