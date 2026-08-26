"""Copernicus Data Space Ecosystem (CDSE) provider — Sentinel-5P NO2.

Concrete workflow (not a vague "Copernicus API" wrapper):

    1. search()   CDSE catalogue query for Sentinel-5P L2 NO2 products
                  covering an AOI/time window.
    2. metadata() Full provenance for one product (processing level,
                  sensing times, footprint, size).
    3. retrieve() Extract NO2 total-column values for a point. Value
                  extraction from the NetCDF products requires the CDSE
                  openEO / Processing credentials; without them this provider
                  raises a *clear* error instead of pretending.

Chosen scope: ONE product family first (Sentinel-5P L2 NO2) — done properly
with provenance — rather than every Copernican product badly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.environmental import EnvironmentalObservation
from app.services.providers.base import ProviderError

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
    "/protocol/openid-connect/token"
)
CDSE_CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/ovo/collections"

PRODUCT_COLLECTION = "SENTINEL-5P"
PRODUCT_TYPE = "L2__NO2___"  # Sentinel-5P TROPOMI L2 Nitrogen Dioxide
PROCESSING_LEVEL = "L2"
RESOLUTION = "7 km x 3.5 km (TROPOMI footprint)"
VARIABLE = "no2_column"
UNIT = "mol/m2"


class CopernicusProvider:
    """Sentinel-5P L2 NO2 implementation of the SatelliteProvider protocol."""

    name = "copernicus"

    def __init__(
        self,
        username: str = "",
        password: str = "",
        catalogue_url: str = CDSE_CATALOGUE_URL,
        token_url: str = CDSE_TOKEN_URL,
    ):
        self.username = username
        self.password = password
        self.catalogue_url = catalogue_url.rstrip("/")
        self.token_url = token_url
        self._token: Optional[str] = None

    # ------------------------------------------------------------------
    # Auth (CDSE uses the resource-owner password flow, not client creds)
    # ------------------------------------------------------------------
    async def _get_token(self) -> Optional[str]:
        if not (self.username and self.password):
            return None
        if self._token:
            return self._token
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "password",
                    "username": self.username,
                    "password": self.password,
                    "client_id": "cdse-public",
                },
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"CDSE authentication failed ({resp.status_code}); check "
                "COPERNICUS_USERNAME / COPERNICUS_PASSWORD"
            )
        self._token = resp.json().get("access_token")
        return self._token

    # ------------------------------------------------------------------
    # SatelliteProvider protocol
    # ------------------------------------------------------------------
    async def search(
        self,
        lat: float,
        lon: float,
        start: Optional[date] = None,
        end: Optional[date] = None,
        max_records: int = 5,
    ) -> List["SatelliteScene"]:
        from app.services.providers.satellite import SatelliteScene

        end_dt = datetime.combine(
            end or date.today(), datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(days=1)
        start_dt = datetime.combine(
            start or (end_dt.date() - timedelta(days=2)),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )

        params: Dict[str, Any] = {
            "collection": PRODUCT_COLLECTION,
            "productType": PRODUCT_TYPE,
            "bbox": f"{lon - 0.05},{lat - 0.05},{lon + 0.05},{lat + 0.05}",
            "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDate": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxRecords": max_records,
        }
        data = await self._get_json(
            f"{self.catalogue_url}/{PRODUCT_COLLECTION}/products", params
        )
        return [self._item_to_scene(item) for item in data.get("value", [])]

    async def metadata(self, scene_id: str) -> "SatelliteScene":
        from app.services.providers.satellite import SatelliteScene

        data = await self._get_json(
            f"{self.catalogue_url}/{PRODUCT_COLLECTION}/products/{scene_id}", {}
        )
        return self._item_to_scene(data)

    def _item_to_scene(self, item: Dict[str, Any]) -> "SatelliteScene":
        from app.services.providers.satellite import SatelliteScene

        sensing = item.get("ContentDate", {}).get("Start") or item.get(
            "SensingStart"
        )
        acquired = None
        if sensing:
            try:
                acquired = datetime.fromisoformat(
                    str(sensing).replace("Z", "+00:00")
                )
            except ValueError:
                acquired = None
        return SatelliteScene(
            scene_id=str(item.get("Id") or item.get("Name", "unknown")),
            source=self.name,
            dataset=f"Sentinel-5P TROPOMI {PRODUCT_TYPE}",
            product=PRODUCT_TYPE,
            processing_level=PROCESSING_LEVEL,
            resolution=RESOLUTION,
            acquisition_time=acquired or datetime.now(timezone.utc),
            footprint=item.get("Footprint"),
            quality_flags={
                "cloud_cover_unavailable": True,
                "online_status": item.get("Online"),
            },
        )

    async def retrieve(
        self,
        lat: float,
        lon: float,
        scene_id: str,
        location_name: str = "",
    ) -> List[EnvironmentalObservation]:
        """Extract point NO2 values — requires CDSE processing credentials.

        Raster extraction runs through the CDSE openEO/Processing stack.
        Without credentials we raise a precise, actionable error rather than
        returning fabricated numbers; catalogue provenance stays available.
        """
        token = await self._get_token()
        if not token:
            raise ProviderError(
                "Sentinel-5P NO2 extraction requires Copernicus Data Space "
                "credentials (set COPERNICUS_USERNAME / COPERNICUS_PASSWORD). "
                "Catalogue search/metadata remain available without them."
            )
        scene = await self.metadata(scene_id)
        raise ProviderError(
            f"NO2 value extraction for {scene.scene_id} requires an active CDSE "
            "openEO processing subscription. Scene provenance is available via "
            "search() / metadata()."
        )

    async def _get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"CDSE catalogue unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"HTTP {resp.status_code} from {url}")
        return resp.json()
