"""OpenAQ v3 adapter.

Migrated from the retired v2 ``/v2/latest`` endpoint. The v3 API is
location-centric:

    GET /v3/locations?coordinates=<lat,lon>&radius=<m>   -> nearest locations
    GET /v3/locations/{id}                                -> sensors metadata
    GET /v3/locations/{id}/latest                         -> latest per-sensor values

Raw v3 JSON never escapes this module; results are normalised into canonical
EnvironmentalObservation records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import EnvironmentalProvider, ProviderError

OPENAQ_BASE_URL = "https://api.openaq.org/v3"
# Canonical units for the pollutants we ingest (OpenAQ reports ug/m3).
CANONICAL_UNITS = {
    "pm25": "ug/m3",
    "pm10": "ug/m3",
    "no2": "ug/m3",
    "o3": "ug/m3",
    "so2": "ug/m3",
    "co": "mg/m3",
}


class OpenAQProvider(EnvironmentalProvider):
    name = "openaq"

    def __init__(self, api_key: str, radius_m: int = 1000, base_url: str = OPENAQ_BASE_URL):
        self.api_key = api_key
        self.radius_m = radius_m
        self.base_url = base_url

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key}

    async def fetch_latest(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> List[EnvironmentalObservation]:
        """Fetch latest pollutant measurements near (lat, lon)."""
        if not self.api_key:
            raise ProviderError("OPENAQ_API_KEY not set")

        headers = self._headers()

        # 1. Nearest monitoring location.
        loc_data = await self._get_json(
            f"{self.base_url}/locations",
            params={
                "coordinates": f"{lat},{lon}",
                "radius": self.radius_m,
                "limit": 1,
            },
            headers=headers,
        )
        results = loc_data.get("results") or []
        if not results:
            raise ProviderError("No air quality data available")
        site = results[0]
        site_id = site.get("id")
        observed_at = site.get("datetime", {}).get("utc") if isinstance(
            site.get("datetime"), dict
        ) else None

        # 2. Sensor metadata maps sensor_id -> parameter name (+ unit).
        detail = await self._get_json(
            f"{self.base_url}/locations/{site_id}", headers=headers
        )
        sensor_params: Dict[str, dict] = {}
        for sensor in detail.get("sensors") or []:
            param = (sensor.get("parameter") or {}).get("name")
            if param:
                sensor_params[str(sensor.get("id"))] = sensor.get("parameter")

        # 3. Latest values per sensor.
        latest = await self._get_json(
            f"{self.base_url}/locations/{site_id}/latest", headers=headers
        )
        readings = latest.get("results") or []
        if not readings:
            raise ProviderError("No air quality data available")

        now = datetime.now(timezone.utc)
        observed = (
            datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            if observed_at
            else now
        )

        observations: List[EnvironmentalObservation] = []
        for reading in readings:
            sensor_id = str(reading.get("sensorsId"))
            value = reading.get("value")
            parameter_meta = sensor_params.get(sensor_id)
            if parameter_meta is None or value is None:
                continue
            parameter = parameter_meta.get("name", "unknown")
            unit = (parameter_meta.get("units")) or CANONICAL_UNITS.get(parameter, "unknown")
            observations.append(
                EnvironmentalObservation(
                    source=self.name,
                    variable=parameter,
                    value=float(value),
                    unit=unit,
                    latitude=lat,
                    longitude=lon,
                    location_name=location_name,
                    # --- Timestamp semantics ------------------------------------
                    # observed_at = when the sensor recorded the measurement
                    # acquisition_time = same as observed (direct sensor reading,
                    #   no separate satellite overpass)
                    # retrieved_at = when we fetched it (audit trail)
                    observed_at=observed,
                    acquisition_time=observed,
                    retrieved_at=now,
                    # --- Provenance: unambiguous source attribution -------------
                    dataset="OpenAQ v3",
                    product="latest",
                    processing_level="L2",  # processed sensor data
                    resolution="point",      # station-level reading
                    averaging_period="instantaneous",  # instantaneous sensor reading
                    # OpenAQ does not publish per-reading uncertainty;
                    # None signals "unknown" rather than "zero".
                    uncertainty=None,
                    confidence=0.85,     # verified station, instantaneous sample
                    quality_score=85.0,
                    data_completeness=len(sensor_params) and (
                        len(readings) / max(len(sensor_params), 1)
                    ),
                    quality="verified",
                    # Immutable reproducibility bundle.
                    provenance={
                        "provider": "openaq",
                        "collection": "openaq-v3",
                        "api_version": "v3",
                        "site_id": site_id,
                        "site_name": site.get("name"),
                        "sensor_id": sensor_id,
                        "parameter": parameter,
                        "units": unit,
                        "radius_m": self.radius_m,
                        "retrieved_at": now.isoformat(),
                    },
                    quality_flags={
                        "is_mobile": site.get("isMobile"),
                        "is_analysis": reading.get("isAnalysis"),
                    },
                )
            )
        if not observations:
            raise ProviderError("No air quality data available")
        return observations

    @staticmethod
    def to_reading_payload(
        lat: float,
        lon: float,
        location_name: str,
        observations: List[EnvironmentalObservation],
    ) -> Optional[dict]:
        """Flatten observations into the legacy reading-dict shape used by the DB.

        AQI is computed with the real EPA breakpoint methodology
        (:mod:`app.core.aqi`). OpenAQ "latest" values are *instantaneous*
        sensor readings, NOT EPA-averaged windows — so every AQI produced here
        carries ``methodology_status="non_standard_averaging"`` and is
        explicitly labelled indicative rather than standard-derived.
        """
        from app.core.aqi import calculate_overall_aqi

        pollutants = {}
        units = {}
        for obs in observations:
            if obs.variable in CANONICAL_UNITS:
                pollutants[obs.variable] = obs.value
                units[obs.variable] = obs.unit

        if not pollutants:
            return None

        aqi_record = calculate_overall_aqi(
            pollutants,
            units=units,
            averaging_periods={p: o.averaging_period for p, o in
                               ((o.variable, o) for o in observations)
                               if p in pollutants},
        )
        return {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "aqi": aqi_record["aqi"],
            # Scientific provenance for the AQI number itself.
            "aqi_methodology": aqi_record,
            "pm25": pollutants.get("pm25"),
            "pm10": pollutants.get("pm10"),
            "no2": pollutants.get("no2"),
            "o3": pollutants.get("o3"),
            "co": pollutants.get("co"),
            "so2": pollutants.get("so2"),
            "source": "openaq",
        }
