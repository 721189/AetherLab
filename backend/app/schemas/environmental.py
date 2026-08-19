from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentalReadingBase(BaseModel):
    location_name: str = Field(..., min_length=1, max_length=255)
    lat: float
    lon: float
    source: str = Field(..., min_length=1, max_length=50)


class EnvironmentalReadingResponse(EnvironmentalReadingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[int] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    pressure: Optional[float] = None
    uv_index: Optional[float] = None
    weather_description: Optional[str] = None
    aqi: Optional[int] = None
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    no2: Optional[float] = None
    o3: Optional[float] = None
    co: Optional[float] = None
    so2: Optional[float] = None
    recorded_at: datetime
    created_at: datetime


class EnvironmentalSummary(BaseModel):
    """Compact payload used by the /latest and /historical endpoints."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    temperature: Optional[float] = None
    aqi: Optional[int] = None
    pm25: Optional[float] = None
    recorded_at: datetime

