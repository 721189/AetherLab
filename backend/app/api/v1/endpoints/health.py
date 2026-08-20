"""Service health-check endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.rate_limiter import limiter
from app.dependencies.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
@limiter.limit("60/minute")
def health(request: Request, db: Session = Depends(get_db)):
    """Liveness probe. Reports DB connectivity without crashing when the DB is down."""
    db_status = "unavailable"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:  # pragma: no cover - depends on DB availability
        db_status = "unavailable"

    return {"status": "ok", "database": db_status}
