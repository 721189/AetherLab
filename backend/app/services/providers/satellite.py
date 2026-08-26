"""Satellite data provider protocol + NASA implementation.

Satellite sources (NASA, Copernicus) follow a fundamentally different access
pattern from point-observation APIs: you *search* a catalogue for scenes,
optionally inspect *metadata*, then *retrieve* values. The
:class:`SatelliteProvider` Protocol makes those implementations first-class —
never special cases bolted onto the weather adapter interface.

    SatelliteProvider (Protocol)
        .search(lat, lon, window)      -> list[SatelliteScene]
        .metadata(scene_id)            -> SatelliteScene (full)
        .retrieve(lat, lon, scene_id)  -> list[EnvironmentalObservation]
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import ProviderError


@runtime_checkable
class SatelliteProvider(Protocol):
    """Common interface for catalogue-driven satellite data sources."""

    name: str

    async def search(self, lat, lon, start=None, end=None): ...

    async def metadata(self, scene_id: str): ...

    async def retrieve(self, lat, lon, scene_id: str, location_name: str = ""): ...


class SatelliteScene:
    """Catalogue entry with full provenance."""

    def __init__(
        self,
        *,
        scene_id: str,
        source: str,
        dataset: str,
        product: str,
        processing_level: str,
        resolution: str,
        acquisition_time: datetime,
        footprint: dict | None = None,
        quality_flags: dict | None = None,
    ):
        self.scene_id = scene_id
        self.source = source
        self.dataset = dataset
        self.product = product
        self.processing_level = processing_level
        self.resolution = resolution
        self.acquisition_time = acquisition_time
        self.footprint = footprint or {}
        self.quality_flags = quality_flags or {}

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "source": self.source,
            "dataset": self.dataset,
            "product": self.product,
            "processing_level": self.processing_level,
            "resolution": self.resolution,
            "acquisition_time": self.acquisition_time.isoformat(),
            "quality_flags": self.quality_flags,
        }


# ---------------------------------------------------------------------------
# NASA POWER — meteorological *reanalysis* data.
#
# IMPORTANT TERMINOLOGY: NASA POWER (MERRA-2 atmospheric assimilation) is
# gridded environmental/meteorological model data — NOT satellite imagery and
# NOT a Sentinel/Landsat-class EO raster product. It satisfies the
# SatelliteProvider protocol because it is catalogue-shaped (scene per day),
# but its provenance must always describe it as reanalysis. True EO imagery
# belongs to providers like Copernicus (Sentinel-5P).
# ---------------------------------------------------------------------------

NASA_POWER_URL = "https://power.laarc.nasa.gov/api/temporal/daily/point"


class NASAProvider:
    """NASA POWER daily-point meteorology (MERRA-2 reanalysis).

    Implements :class:`SatelliteProvider` for pipeline uniformity; the
    provenance on every observation states ``dataset="POWER ..."`` with
    processing level L3 so no consumer can mistake it for direct imagery.
    """

    name = "nasa"

    # parameter code -> (canonical variable, unit, description)
    PARAMETERS = {
        "T2M": ("temperature", "celsius", "Temperature at 2 Meters"),
        "RH2M": ("humidity", "percent", "Relative Humidity at 2 Meters"),
        "WS2M": ("wind_speed", "m/s", "Wind Speed at 2 Meters"),
    }

    DATASET = "POWER (MERRA-2 reanalysis)"
    PRODUCT = "reanalysis-daily-point"
    PROCESSING_LEVEL = "L3"
    RESOLUTION = "0.5° x 0.625° (~55 km)"

    def __init__(self, base_url: str = NASA_POWER_URL):
        self.base_url = base_url

    # -- SatelliteProvider protocol -------------------------------------
    async def search(self, lat, lon, start=None, end=None):
        """POWER is a continuous gridded dataset: one 'scene' per day."""
        from datetime import timedelta

        end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
        start = start or end - timedelta(days=1)
        return [
            SatelliteScene(
                scene_id=f"POWER-{start.isoformat()}",
                source=self.name,
                dataset=self.DATASET,
                product=self.PRODUCT,
                processing_level=self.PROCESSING_LEVEL,
                resolution=self.RESOLUTION,
                acquisition_time=datetime(
                    start.year, start.month, start.day, tzinfo=timezone.utc
                ),
            )
        ]

    async def metadata(self, scene_id: str) -> SatelliteScene:
        if not scene_id.startswith("POWER-"):
            raise ProviderError(f"Unknown scene {scene_id!r}")
        day = date.fromisoformat(scene_id.removeprefix("POWER-"))
        return SatelliteScene(
            scene_id=scene_id,
            source=self.name,
            dataset=self.DATASET,
            product=self.PRODUCT,
            processing_level=self.PROCESSING_LEVEL,
            resolution=self.RESOLUTION,
            acquisition_time=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
        )

    async def retrieve(
        self,
        lat: float,
        lon: float,
        scene_id: str,
        location_name: str = "",
    ) -> List[EnvironmentalObservation]:
        loop_day = scene_id.removeprefix("POWER-")
        compact_day = loop_day.replace("-", "")  # POWER keys dates as YYYYMMDD
        params = {
            "parameters": ",".join(self.PARAMETERS),
            "community": "RE",
            "latitude": lat,
            "longitude": lon,
            "start": compact_day,
            "end": compact_day,
            "format": "JSON",
        }
        data = await self._get_json(self.base_url, params=params)

        properties = data.get("properties", {}).get("parameter", {})
        scene = await self.metadata(scene_id)
        now = datetime.now(timezone.utc)

        observations: List[EnvironmentalObservation] = []
        for code, (variable, unit, _desc) in self.PARAMETERS.items():
            series = properties.get(code, {})
            value = series.get(compact_day)
            if value is None or value < -900:  # POWER uses -999 as fill value
                continue
            observations.append(
                EnvironmentalObservation(
                    source="nasa",
                    variable=variable,
                    value=float(value),
                    unit=unit,
                    latitude=lat,
                    longitude=lon,
                    location_name=location_name or None,
                    dataset=f"{self.DATASET} {code}",
                    product=self.PRODUCT,
                    processing_level=self.PROCESSING_LEVEL,
                    resolution=self.RESOLUTION,
                    acquisition_time=scene.acquisition_time,
                    observed_at=scene.acquisition_time,
                    retrieved_at=now,
                    averaging_period="24-hour",  # POWER daily means
                    uncertainty=1.0 if variable == "temperature" else None,
                    confidence=0.8,  # model assimilation, not in-situ measurement
                    quality_score=80.0,
                    data_completeness=len(observations) / len(self.PARAMETERS),
                    quality_flags={"fill_value_masked": True},
                    provenance={
                        "provider": "nasa",
                        "collection": "POWER",
                        "scene_id": scene.scene_id,
                        "product": scene.product,
                        "processing": scene.processing_level,
                        "reanalysis_source": "MERRA-2",
                        "request_url": self.base_url,
                        "retrieved_at": now.isoformat(),
                    },
                    quality="verified",
                )
            )
        if not observations:
            raise ProviderError("No usable NASA POWER values returned")
        return observations

    async def _get_json(self, url: str, *, params: dict) -> dict:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"NASA POWER unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"HTTP {resp.status_code} from {url}")
        return resp.json()
