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

import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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

# CDSE token refresh guard: we never request a new token more than this often,
# and we always prefer the refresh_token when one has been issued.
TOKEN_SKEW_SECONDS = 30


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
        # CDSE token lifecycle state — stored server-side only. We cache the
        # access token and its expiry, and refresh with the refresh_token
        # instead of re-authenticating on every request.
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Auth (CDSE uses the resource-owner password / refresh flows).
    #
    # Lifecycle:
    #    request -> access token valid? -> yes: attach and request
    #                                   -> no:  refresh (or initial password
    #                                           grant) then retry
    # We never authenticate on every request and never send the raw password
    # more than once per token lifetime.
    # ------------------------------------------------------------------
    async def _ensure_token(self) -> str:
        """Return a non-expired access token, refreshing if necessary."""
        if self._access_token and self._expires_at:
            skew = timedelta(seconds=TOKEN_SKEW_SECONDS)
            if datetime.now(timezone.utc) < (self._expires_at - skew):
                return self._access_token

        if self._refresh_token:
            try:
                self._access_token = await self._request_token(
                    {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
                )
                return self._access_token
            except ProviderError:
                # refresh token invalid/expired -> fall through to password grant
                self._refresh_token = None

        if not (self.username and self.password):
            raise ProviderError(
                "CDSE requires COPERNICUS_USERNAME / COPERNICUS_PASSWORD to "
                "obtain an access token (no refresh token available)."
            )
        token = await self._request_token(
            {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": "cdse-public",
            }
        )
        return token

    async def _request_token(self, payload: Dict[str, str]) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self.token_url, data=payload)
        if resp.status_code != 200:
            raise ProviderError(
                f"CDSE token request failed ({resp.status_code}); check "
                "COPERNICUS_USERNAME / COPERNICUS_PASSWORD / token state"
            )
        body = resp.json()
        self._access_token = body.get("access_token")
        self._refresh_token = body.get("refresh_token")
        expires_in = body.get("expires_in")
        if expires_in:
            self._expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=int(expires_in)
            )
        if not self._access_token:
            raise ProviderError("CDSE token response contained no access_token")
        return self._access_token

    # ------------------------------------------------------------------
    # SatelliteProvider protocol
    # ------------------------------------------------------------------
    async def search(
        self,
        lat: float,
        lon: float,
        start: Optional[date] = None,
        end: Optional[date] = None,
        bbox: Optional[List[float]] = None,
        collection: str = PRODUCT_COLLECTION,
        max_records: int = 5,
    ) -> List["SatelliteScene"]:
        from datetime import timedelta

        from app.services.providers.satellite import SatelliteScene

        end_dt = datetime.combine(
            end or date.today(), datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(days=1)
        start_dt = datetime.combine(
            start or (end_dt.date() - timedelta(days=2)),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )

        if bbox is None:
            bbox = [lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05]
        params: Dict[str, Any] = {
            "collection": collection,
            "productType": PRODUCT_TYPE,
            "bbox": ",".join(f"{c:.6f}" for c in bbox),
            "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDate": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxRecords": max_records,
        }
        data = await self._get_json(
            f"{self.catalogue_url}/{collection}/products", params
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

        # The CDSE catalogue exposes downloadable assets per product; surface
        # them so scene discovery returns retrievable artifacts (STAC-style).
        assets: Dict[str, Any] = {}
        raw_assets = item.get("Assets") or {}
        for name, asset in raw_assets.items():
            href = asset.get("Href") or asset.get("Url")
            if href:
                assets[name] = {
                    "href": href,
                    "title": asset.get("Title"),
                    "roles": [asset.get("Role")] if asset.get("Role") else [],
                }

        return SatelliteScene(
            scene_id=str(item.get("Id") or item.get("Name", "unknown")),
            source=self.name,
            dataset=f"Sentinel-5P TROPOMI {PRODUCT_TYPE}",
            collection=PRODUCT_COLLECTION,
            product=PRODUCT_TYPE,
            processing_level=PROCESSING_LEVEL,
            resolution=RESOLUTION,
            acquisition_time=acquired or datetime.now(timezone.utc),
            footprint=item.get("Footprint"),
            quality_flags={
                "cloud_cover_unavailable": True,
                "online_status": item.get("Online"),
            },
            assets=assets,
        )

    async def retrieve(
        self,
        lat: float,
        lon: float,
        scene_id: str,
        location_name: str = "",
        product_path: Optional[str] = None,
    ) -> List[EnvironmentalObservation]:
        """Extract quality-filtered NO2 for a point from a Sentinel-5P product.

        Pipeline (steps 13–14):
            CDSE product (NetCDF) -> decode -> quality filtering ->
            invalid pixels removed -> AOI filter -> aggregation -> observation

        ``product_path`` lets a locally-downloaded product be processed offline
        (used by tests/e2e). Without a local file AND without credentials we
        raise a precise error — before any network I/O.
        """
        from app.services.processing.sentinel_no2 import extract_no2_from_arrays

        if not product_path and not (self.username and self.password):
            raise ProviderError(
                "Sentinel-5P NO2 extraction requires Copernicus Data Space "
                "credentials (COPERNICUS_USERNAME / COPERNICUS_PASSWORD) or a "
                "local product file (`product_path`). Catalogue search/metadata "
                "remain available without them."
            )

        scene = await self.metadata(scene_id)

        if product_path:
            product_arrays = self._decode_product(product_path)
            agg = extract_no2_from_arrays(product_arrays, lat, lon)
        else:
            # Only reachable when credentials exist but no local file: live
            # CDSE extraction would require an authenticated openEO workload.
            await self._ensure_token()
            raise ProviderError(
                f"NO2 value extraction for {scene.scene_id} requires an active "
                "CDSE openEO processing subscription or a local product file. "
                "Scene provenance is available via search() / metadata(); "
                "offline processing is supported via `product_path`."
            )

        now = datetime.now(timezone.utc)
        total = agg["methodology"]["pixels_input"]
        used = agg["methodology"]["pixels_used"]
        return [
            EnvironmentalObservation(
                source=self.name,
                variable=VARIABLE,
                value=agg["value"],
                unit=UNIT,
                latitude=lat,
                longitude=lon,
                location_name=location_name or None,
                dataset="Sentinel-5P TROPOMI L2",
                product=scene.product,
                processing_level=scene.processing_level,
                resolution=scene.resolution,
                acquisition_time=scene.acquisition_time,
                observed_at=scene.acquisition_time,
                retrieved_at=now,
                averaging_period="instantaneous",
                confidence=0.7,
                quality_score=70.0,
                data_completeness=used / max(1, total),
                quality_flags=agg["methodology"],
                quality="preliminary",
                provenance={
                    "provider": "copernicus",
                    "collection": scene.collection,
                    "scene_id": scene.scene_id,
                    "product": scene.product,
                    "processing": scene.processing_level,
                    "source_url": (
                        next(iter(scene.assets.values())).get("href")
                        if scene.assets else None
                    ),
                    "processing_level": scene.processing_level,
                    "retrieved_at": now.isoformat(),
                    "quality_methodology": agg["methodology"],
                },
            )
        ]

    @staticmethod
    def _decode_product(path: str) -> Dict[str, Any]:
        """Decode a TROPOMI L2 NetCDF product -> flat arrays by variable.

        Uses xarray with the netCDF4 engine. Raises a clear error if the EO
        dependencies aren't installed.
        """
        try:
            import xarray as xr
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "Sentinel-5P product extraction requires 'xarray' and a NetCDF "
                "backend (e.g. netCDF4/h5netcdf). Install them to enable CDSE "
                "NO2 retrieval."
            ) from exc

        from app.services.processing.sentinel_no2 import (
            NO2_DATA_VAR, NO2_LAT_VAR, NO2_LON_VAR, NO2_QA_VAR,
        )

        ds = xr.open_dataset(path, engine="netcdf4")
        try:
            data = ds[NO2_DATA_VAR].values
            qa = ds[NO2_QA_VAR].values
            lat = ds[NO2_LAT_VAR].values
            lon = ds[NO2_LON_VAR].values
        finally:
            ds.close()
        return {
            NO2_DATA_VAR: data.flatten(),
            NO2_QA_VAR: qa.flatten(),
            NO2_LAT_VAR: lat.flatten(),
            NO2_LON_VAR: lon.flatten(),
        }

    async def _get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"CDSE catalogue unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"HTTP {resp.status_code} from {url}")
        return resp.json()
