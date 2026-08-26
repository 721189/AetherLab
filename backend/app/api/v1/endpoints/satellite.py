"""Provider-independent satellite data API.

Public surface for the SatelliteProvider abstraction:

    GET  /satellite/scenes?lat=&lon=&source=       catalogue search
    GET  /satellite/scenes/{scene_id}?source=      scene metadata
    POST /satellite/observations                    retrieve + persist values

All sources (nasa, copernicus, ...) are addressed through the same
interface — adding a provider never adds an endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.rate_limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.environmental import EnvironmentalObservation
from app.services.environmental import ProviderRegistry

router = APIRouter(prefix="/satellite", tags=["Satellite"])


def _provider(source: str):
    try:
        return ProviderRegistry.get(source)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown satellite source {source!r}; "
            f"available: {ProviderRegistry.names()}",
        )


@router.get(
    "/scenes",
    summary="Search satellite scenes covering a point",
    description="Catalogue search across the selected provider (nasa/copernicus).",
)
@limiter.limit("30/minute")
async def search_scenes(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    source: str = Query("nasa"),
    current_user: User = Depends(get_current_user),
):
    provider = _provider(source)
    from datetime import date

    scenes = await provider.search(lat, lon)
    return {
        "source": source,
        "count": len(scenes),
        "scenes": [s.to_dict() for s in scenes],
    }


@router.get(
    "/scenes/{scene_id}",
    summary="Full provenance for one satellite scene",
)
@limiter.limit("30/minute")
async def scene_metadata(
    request: Request,
    scene_id: str,
    source: str = Query("nasa"),
    current_user: User = Depends(get_current_user),
):
    provider = _provider(source)
    try:
        scene = await provider.metadata(scene_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return scene.to_dict()


class ObservationRequest(BaseModel):
    lat: float
    lon: float
    location_name: str = ""
    source: str = "nasa"
    scene_id: Optional[str] = None


@router.post(
    "/observations",
    summary="Retrieve and persist satellite observations for a point",
    description=(
        "Runs the canonical ingestion path for the requested satellite "
        "source and returns the stored observations with full provenance."
    ),
)
@limiter.limit("10/minute")
async def retrieve_observations(
    request: Request,
    body: ObservationRequest,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = _provider(body.source)
    scene_id = body.scene_id
    if not scene_id:
        scenes = await provider.search(body.lat, body.lon)
        if not scenes:
            raise HTTPException(
                status_code=404,
                detail=f"No {body.source} scenes cover this point",
            )
        scene_id = scenes[0].scene_id

    try:
        observations = await provider.retrieve(
            body.lat, body.lon, scene_id, body.location_name
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    from app.services.environmental import EnvironmentalObservationRepository

    stored = EnvironmentalObservationRepository(db).create_many(observations)
    return {
        "source": body.source,
        "scene_id": scene_id,
        "stored": len(stored),
        "observations": [
            o.model_dump(mode="json") for o in observations
        ],
    }