from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.environmental_reading import EnvironmentalReading


class EnvironmentalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> EnvironmentalReading:
        # Only persist keys that map to model columns so unknown provider
        # extras (e.g. "error") never blow up on INSERT.
        columns = {
            c.name for c in EnvironmentalReading.__table__.columns
        }
        payload = {k: v for k, v in data.items() if k in columns}
        reading = EnvironmentalReading(**payload)
        self.db.add(reading)
        self.db.commit()
        self.db.refresh(reading)
        return reading

    def get_latest_by_location(
        self,
        location_name: str,
        limit: int = 10,
    ) -> List[EnvironmentalReading]:
        return (
            self.db.query(EnvironmentalReading)
            .filter(EnvironmentalReading.location_name == location_name)
            .order_by(
                EnvironmentalReading.recorded_at.desc(),
                EnvironmentalReading.id.desc(),
            )
            .limit(limit)
            .all()
        )

    def get_by_location_since(
        self,
        location_name: str,
        since: datetime,
    ) -> List[EnvironmentalReading]:
        return (
            self.db.query(EnvironmentalReading)
            .filter(
                EnvironmentalReading.location_name == location_name,
                EnvironmentalReading.recorded_at >= since,
            )
            .order_by(
                EnvironmentalReading.recorded_at.desc(),
                EnvironmentalReading.id.desc(),
            )
            .all()
        )

    def get_by_geofence(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        limit: int = 100,
    ) -> List[EnvironmentalReading]:
        """Readings within a simplified lat/lon bounding box.

        A production deployment should replace this with PostGIS/geoalchemy2;
        this approximation is fine for coarse "nearby" queries.
        """
        degrees = radius_km / 111.0
        return (
            self.db.query(EnvironmentalReading)
            .filter(
                EnvironmentalReading.lat.between(lat - degrees, lat + degrees),
                EnvironmentalReading.lon.between(lon - degrees, lon + degrees),
            )
            .limit(limit)
            .all()
        )
