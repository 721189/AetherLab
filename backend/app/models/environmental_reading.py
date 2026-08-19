from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Recognised data source identifiers for ingested readings.
ENVIRONMENTAL_SOURCES = ("openweather", "openaq", "nasa", "manual")


class EnvironmentalReading(Base):
    """A single point-in-time environmental observation for a location.

    Readings are intentionally denormalised: each row stores the full weather
    + air-quality snapshot captured at ``recorded_at`` so historical queries
    are trivial and provider-specific joins are unnecessary.
    """

    __tablename__ = "environmental_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Location
    location_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)

    # Weather data (OpenWeather)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    feels_like: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    uv_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Air quality data (OpenAQ)
    aqi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pm25: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10: Mapped[float | None] = mapped_column(Float, nullable=True)
    no2: Mapped[float | None] = mapped_column(Float, nullable=True)
    o3: Mapped[float | None] = mapped_column(Float, nullable=True)
    co: Mapped[float | None] = mapped_column(Float, nullable=True)
    so2: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Metadata
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<EnvironmentalReading(location={self.location_name!r}, "
            f"aqi={self.aqi}, temp={self.temperature})>"
        )
