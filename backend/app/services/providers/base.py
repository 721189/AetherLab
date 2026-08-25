"""Provider adapter base class.

Adapters encapsulate everything provider-specific — endpoint URLs, auth,
raw JSON shapes — and expose a single canonical interface:

    adapter.fetch_latest(...)  -> list[EnvironmentalObservation]

The application never imports provider JSON shapes outside these modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.environmental import EnvironmentalObservation

DEFAULT_TIMEOUT = 15.0


class ProviderError(Exception):
    """Raised when a provider cannot be reached or returns unusable data."""


class EnvironmentalProvider(ABC):
    """Common interface for environmental data providers."""

    name: str = "abstract"

    @abstractmethod
    async def fetch_latest(
        self,
        lat: float,
        lon: float,
        location_name: str,
    ) -> List[EnvironmentalObservation]:
        """Return normalised observations for the given coordinates."""

    # ------------------------------------------------------------------
    # Shared HTTP helper
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_json(
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{url} unreachable: {exc}") from exc
        if response.status_code != 200:
            detail = getattr(response, "text", "")[:200]
            raise ProviderError(
                f"HTTP {response.status_code} from {url}: {detail}"
            )
        return response.json()
