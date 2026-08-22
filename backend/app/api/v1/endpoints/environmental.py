from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.models.environmental_reading import EnvironmentalReading
from app.schemas.environmental import (
    EnvironmentalReadingResponse,
    EnvironmentalSummary,
)
from app.services.environmental_service import EnvironmentalService

router = APIRouter(prefix="/environmental", tags=["Environmental"])


@router.get(
    "/latest",
    response_model=list[EnvironmentalSummary],
    summary="Get the latest environmental readings",
    description="Return the most recent readings recorded for a location.",
    response_description="A list of the latest environmental summaries",
)
def get_latest_environmental(
    location_name: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return the most recent readings recorded for a location."""
    service = EnvironmentalService(db)
    readings = service.get_latest_readings(location_name, limit)
    return [EnvironmentalSummary.model_validate(r) for r in readings]


@router.get(
    "/historical",
    response_model=list[EnvironmentalSummary],
    summary="Get historical environmental readings",
    description=(
        "Return readings recorded for a location within the last ``hours``."
    ),
    response_description="A list of historical environmental summaries",
)
def get_historical_environmental(
    location_name: str = Query(..., min_length=1, max_length=255),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Return readings recorded for a location within the last ``hours``."""
    service = EnvironmentalService(db)
    readings = service.get_historical_readings(location_name, hours)
    return [EnvironmentalSummary.model_validate(r) for r in readings]


@router.get(
    "/readings/{reading_id}",
    response_model=EnvironmentalReadingResponse,
    summary="Get a single environmental reading",
    description="Return a single fully-detailed environmental reading by ID.",
    response_description="The detailed environmental reading",
)
def get_reading(
    reading_id: int,
    db: Session = Depends(get_db),
):
    """Return a single fully-detailed environmental reading by ID."""
    reading = db.get(EnvironmentalReading, reading_id)
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reading not found",
        )
    return reading


@router.get(
    "/",
    response_model=list[EnvironmentalSummary],
    summary="Get readings by geographic filter",
    description=(
        "Return readings near a geographic point within a radius (a simplified "
        "geofence)."
    ),
    response_description="A list of environmental summaries near the point",
)
def get_readings_by_filter(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return readings near a geographic point (simplified geofence)."""
    service = EnvironmentalService(db)
    readings = service.repo.get_by_geofence(lat, lon, radius_km)
    return [EnvironmentalSummary.model_validate(r) for r in readings]
