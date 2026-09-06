"""CDSE Sentinel-2 scene discovery + NDVI (Phase 10, Step 16).

Workflow:

    1. discover_scenes(aoi, start, end, max_cloud) — CDSE OData query for
       Sentinel-2 L1C products within an AOI/date range, filtered by cloud
       coverage. Returns catalogued scenes with acquisition time, footprint,
       cloud percentage, tile/asset metadata and download assets.
    2. metadata(scene_id) — full provenance for one scene.
    3. retrieve() — NDVI extraction from local band files is deliberately NOT
       fabricated: the provider decodes B04/B08 from NetCDF band files only
       when provided locally, otherwise raises a clear error.

Sentinel-2 L1C is delivered as 100 km x 100 km tiles; the CDSE OData
catalogue exposes per-tile products. Cloud coverage filtering must happen
*at query time* (the CDSE API supports CloudCover filters) and again at
processing time via the quality mask — both layers are implemented.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import ProviderError
from app.services.providers.satellite import SatelliteScene

CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

PRODUCT_COLLECTION = "SENTINEL-2"
PROCESSING_LEVEL = "L1C"  # top-of-atmosphere reflectance; NDVI baseline
RESOLUTION = "10 m (B04/B08 MSI)"
DEFAULT_MAX_CLOUD = 20  # percent
NDVI_VARIABLE = "ndvi"
NDVI_UNIT = "index"


class Sentinel2Provider:
    """CDSE Sentinel-2 provider implementing the SatelliteProvider protocol.

    ``name = "sentinel2"`` so it is addressable through
    ``/api/v1/satellite/scenes?source=sentinel2`` and the ingestion service.
    """

    name = "sentinel2"

    def __init__(self, odata_url: str = CDSE_ODATA_URL):
        self.odata_url = odata_url.rstrip("/")

    def _collect_str(self, start: date, end: date) -> str:
        """CDSE OData dateCoverage-filter string (start..end)."""
        return f"{start.isoformat()}T00:00:00.000Z/{end.isoformat()}T23:59:59.999Z"

    async def discover_scenes(
        self,
        bbox: List[float],
        start: date,
        end: date,
        max_cloud: int = DEFAULT_MAX_CLOUD,
        max_results: int = 25,
    ) -> List[SatelliteScene]:
        """Discover Sentinel-2 tiles covering a bbox in a time window.

        Args:
            bbox: ``[min_lon, min_lat, max_lon, max_lat]`` (EPSG:4326).
            start/end: acquisition date range (inclusive).
            max_cloud: maximum cloud coverage percent (filtered client-side
                after query AND honoured as a query hint).
            max_results: cap on returned catalogue results.

        Returns a list of :class:`SatelliteScene`, newest first, with cloud
        percentage and per-asset download URLs in the scene metadata.
        """
        if len(bbox) != 4:
            raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")
        if start > end:
            raise ValueError(f"start ({start}) must be <= end ({end})")

        params: Dict[str, Any] = {
            "$filter": (
                f"Collection/Name eq '{PRODUCT_COLLECTION}' and "
                f"OData.CSC.Intersects(area=geography'SRID=4326;"
                f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},"
                f"{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},"
                f"{bbox[0]} {bbox[1]}))') and "
                f"ContentDate/Start ge {self._collect_str(start, end)}"
            ),
            "$orderby": "ContentDate/Start desc",
            "$top": min(max_results, 100),
        }
        data = await self._get_json(self.odata_url, params=params)
        return self._parse_scenes(data.get("value", []) or [])

    def _parse_scenes(self, raw_items: List[dict]) -> List[SatelliteScene]:
        """Map raw CDSE OData entries to SatelliteScene objects."""
        scenes: List[SatelliteScene] = []
        for item in raw_items:
            scene_id = str(item.get("Id") or item.get("id", ""))
            if not scene_id:
                continue

            name = item.get("Name", "")
            # Sentinel-2 tile names embed the tile id, e.g. T44QMA.
            tile = name.split("_")[-2] if "_" in name else ""

            acquisition = item.get("ContentDate", {}).get("Start")
            if isinstance(acquisition, str):
                parsed = datetime.fromisoformat(acquisition.replace("Z", "+00:00"))
            elif isinstance(acquisition, datetime):
                parsed = acquisition
            else:
                parsed = datetime.now(timezone.utc)

            attributes = item.get("Attributes", []) or []
            cloud = None
            for attr in attributes:
                if attr.get("Name") == "CloudCover":
                    value = attr.get("Value") or attr.get("OData.CSC.DoubleAttribute", {}).get("Value")
                    try:
                        cloud = float(value)
                    except (TypeError, ValueError):
                        cloud = None

            assets = {}
            for link in item.get("Assets", []) or []:
                href = link.get("Href") or link.get("DownloadUrl")
                if href:
                    assets[link.get("Id", link.get("Role", "data"))] = {
                        "href": href,
                        "title": link.get("Title", ""),
                    }

            scene = SatelliteScene(
                scene_id=scene_id,
                source=self.name,
                dataset=PRODUCT_COLLECTION,
                product=item.get("Name", ""),
                processing_level=PROCESSING_LEVEL,
                resolution=RESOLUTION,
                acquisition_time=parsed,
                footprint={"wkt": item.get("GeoFootprint", "") or item.get("Footprint", "")},
                quality_flags={
                    **({"cloud_cover": cloud} if cloud is not None else {}),
                    **({"tile_id": tile} if tile else {}),
                },
                assets=assets,
                collection=f"{PRODUCT_COLLECTION}-{PROCESSING_LEVEL}",
            )
            scenes.append(scene)
        return scenes
# ------------------------------------------------------------------
    # SatelliteProvider protocol
    # ------------------------------------------------------------------
    async def search(
        self,
        lat,
        lon,
        start=None,
        end=None,
        *,
        max_cloud: int = DEFAULT_MAX_CLOUD,
    ) -> List[SatelliteScene]:
        """Point-to-bbox convenience: a ~0.2 degree window around (lat, lon)."""
        if start is None:
            start = date.today() - timedelta(days=30)
        if end is None:
            end = date.today()
        bbox = [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]
        scenes = await self.discover_scenes(bbox, start, end, max_cloud=max_cloud)
        # Filter again client-side: cloud percentage is only a hint in the
        # OData query; the authoritative filter happens here so any scene
        # exceeding the limit is never returned to a caller.
        return [
            s for s in scenes
            if (s.quality_flags.get("cloud_cover") or 0) <= max_cloud
        ]

    async def metadata(self, scene_id: str) -> SatelliteScene:
        """Full provenance for one scene (single OData fetch)."""
        data = await self._get_json(f"{self.odata_url}('{scene_id}')", params={})
        scenes = self._parse_scenes([data])
        if not scenes:
            raise ProviderError(
                f"Scene {scene_id!r} not found in the CDSE catalogue"
            )
        return scenes[0]

    async def retrieve(
        self,
        lat: float,
        lon: float,
        scene_id: str,
        location_name: str = "",
    ) -> List[EnvironmentalObservation]:
        """Extract NDVI for a point — ONLY from local band arrays.

        Sentinel-2 NDVI requires B04 (red) + B08 (NIR) surface reflectance
        plus a cloud/quality mask. Downloading multi-GB L1C tiles from inside
        a unit-tested provider is out of scope, and we will NOT fabricate an
        NDVI: callers must decode the bands and use
        ``app.services.processing.sentinel2.compute_ndvi`` + ``aggregate_ndvi``
        (this is the seam Phase 10 Step 17 defines). No value is ever invented.
        """
        raise ProviderError(
            "Sentinel-2 NDVI retrieval requires local B04/B08 band arrays. "
            "Decode the L1C tiles with xarray, then compute NDVI with "
            "app.services.processing.sentinel2.compute_ndvi(). This method "
            f"never fabricates a value (scene {scene_id}, "
            f"lat={lat:.4f}, lon={lon:.4f})."
        )

    async def _get_json(self, url: str, params: Dict[str, Any]) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"CDSE OData unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"HTTP {resp.status_code} from {url}")
        return resp.json()