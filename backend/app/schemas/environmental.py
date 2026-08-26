from datetime import datetime
from typing import Literal, Optional

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


# ---------------------------------------------------------------------------
# Canonical provider-independent observation model.
#
# Every provider adapter (OpenAQ v3, OpenWeather, NASA, Copernicus, ...)
# normalises its raw JSON into EnvironmentalObservation records so downstream
# consumers never see provider-specific payloads.
# ---------------------------------------------------------------------------

SourceName = Literal["openweather", "openaq", "nasa", "copernicus", "manual"]
QualityFlag = Literal["verified", "unverified", "preliminary"]


class EnvironmentalObservation(BaseModel):
    """A single normalised measurement from any provider.

    Provenance fields (dataset/product/processing_level/resolution/
    acquisition_time) matter most for satellite sources — every observation
    can answer "where exactly did this number come from?".
    """

    source: SourceName
    variable: str = Field(description="Canonical variable, e.g. temperature, pm25")
    value: Optional[float] = Field(default=None, description="Measured value")
    unit: str = Field(description="Unit of measure, e.g. celsius, ug/m3")
    latitude: float
    longitude: float
    location_name: Optional[str] = None

    # --- Provenance -----------------------------------------------------
    dataset: Optional[str] = Field(
        default=None, description="Source dataset, e.g. Sentinel-5P OFFL/L3__NO2"
    )
    product: Optional[str] = Field(default=None, description="Product identifier")
    processing_level: Optional[str] = Field(
        default=None, description="Processing level, e.g. L2, L3"
    )
    resolution: Optional[str] = Field(
        default=None, description="Spatial resolution, e.g. '5.5 km x 7 km'"
    )
    acquisition_time: Optional[datetime] = Field(
        default=None, description="Satellite overpass / sensor acquisition time"
    )
    observed_at: Optional[datetime] = Field(
        default=None, description="When the phenomenon was measured by the source"
    )
    retrieved_at: Optional[datetime] = Field(
        default=None, description="When we fetched it"
    )
    averaging_period: str = Field(
        default="unknown",
        description=(
            "Aggregation window of the measurement, e.g. '1-hour', '8-hour', "
            "'24-hour'. AQI methodology is only valid for the EPA-defined "
            "window per pollutant; 'unknown' marks instantaneous readings."
        ),
    )
    uncertainty: Optional[float] = Field(
        default=None,
        description="Provider-stated or estimated measurement uncertainty (+/- in unit)",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in this single observation (0..1)",
    )
    quality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Numeric quality score (0-100) complementing the quality flag",
    )
    data_completeness: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of expected variables actually delivered by the source "
            "in this fetch (0..1)"
        ),
    )
    provenance: dict = Field(
        default_factory=dict,
        description=(
            "Immutable provider-provenance bundle for reproducibility: "
            "provider, collection, scene_id, processing algorithm/version, "
            "software version, CRS, geometry/AOI, cloud percentage, bands..."
        ),
    )
    quality_flags: dict = Field(
        default_factory=dict,
        description="Provider-specific quality flags (cloud cover, QA values...)",
    )
    quality: QualityFlag = "unverified"

