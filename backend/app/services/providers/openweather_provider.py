"""OpenWeather adapter (current weather endpoint).

Normalises the OpenWeather JSON payload into canonical
EnvironmentalObservation records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import EnvironmentalProvider, ProviderError

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class OpenWeatherProvider(EnvironmentalProvider):
    name = "openweather"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def fetch_latest(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> List[EnvironmentalObservation]:
        if not self.api_key:
            raise ProviderError("OPENWEATHER_API_KEY not set")

        data = await self._get_json(
            OPENWEATHER_URL,
            params={"lat": lat, "lon": lon, "appid": self.api_key, "units": "metric"},
        )

        main = data.get("main", {})
        wind = data.get("wind", {})
        now = datetime.now(timezone.utc)
        observed = datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc)

        variables = {
            "temperature": ("celsius", main.get("temp")),
            "feels_like": ("celsius", main.get("feels_like")),
            "humidity": ("percent", main.get("humidity")),
            "pressure": ("hPa", main.get("pressure")),
            "wind_speed": ("m/s", wind.get("speed")),
            "wind_direction": ("degrees", wind.get("deg")),
        }
        # NOTE: uv_index deliberately NOT ingested here — the /data/2.5/weather
        # current-weather endpoint does not reliably return it; it belongs to a
        # separate OpenWeather UV product and would silently be None/stale.

        observations: List[EnvironmentalObservation] = []
        for variable, (unit, value) in variables.items():
            if value is None:
                continue
            observations.append(
                EnvironmentalObservation(
                    source=self.name,
                    variable=variable,
                    value=float(value),
                    unit=unit,
                    latitude=lat,
                    longitude=lon,
                    location_name=location_name,
                    # --- Timestamp semantics ------------------------------------
                    # observed_at = when the measurement was taken by the provider
                    # acquisition_time = same as observed for current-weather (no
                    #   separate satellite overpass — this is a direct reading)
                    # retrieved_at = when we fetched it (provenance audit trail)
                    observed_at=observed,
                    acquisition_time=observed,
                    retrieved_at=now,
                    # --- Provenance: unambiguous source attribution -------------
                    dataset="OpenWeather Current Weather API",
                    product="current",
                    processing_level="L2",  # processed product (not raw instrument)
                    resolution="point",      # station / grid-point reading
                    averaging_period="instantaneous",  # current weather, not averaged
                    # OpenWeather does not publish per-variable uncertainty;
                    # None signals "unknown" rather than "zero" (which would be
                    # a false precision claim).
                    uncertainty=None,
                    confidence=0.9,       # official provider, verified account
                    quality_score=90.0,
                    data_completeness=len(variables) / (len(variables) + 1),
                    quality="verified",
                    # Immutable reproducibility bundle: enough to re-fetch the
                    # exact same payload from the provider.
                    provenance={
                        "provider": "openweather",
                        "collection": "openweather-current",
                        "api_version": "2.5",
                        "endpoint": OPENWEATHER_URL,
                        "station_id": data.get("id"),
                        "station_name": data.get("name"),
                        "raw_dt": data.get("dt"),
                        "timezone_offset_sec": data.get("timezone"),
                        "retrieved_at": now.isoformat(),
                    },
                    quality_flags={
                        "clouds_pct": data.get("clouds", {}).get("all"),
                        "visibility_m": data.get("visibility"),
                        "weather_id": data.get("weather", [{}])[0].get("id") if data.get("weather") else None,
                    },
                )
            )
        return observations

    @staticmethod
    def to_reading_payload(
        lat: float,
        lon: float,
        location_name: str,
        observations: List[EnvironmentalObservation],
    ) -> dict:
        """Flatten observations into the legacy reading-dict shape used by the DB."""
        values = {o.variable: o.value for o in observations}
        description = None
        return {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "temperature": values.get("temperature"),
            "feels_like": values.get("feels_like"),
            "humidity": values.get("humidity"),
            "wind_speed": values.get("wind_speed"),
            "wind_direction": values.get("wind_direction"),
            "pressure": values.get("pressure"),
            "uv_index": values.get("uv_index"),
            "weather_description": description,
            "source": "openweather",
        }
