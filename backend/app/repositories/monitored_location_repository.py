"""Repository for monitored locations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.monitored_location import MonitoredLocation


class MonitoredLocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_enabled(self) -> list[MonitoredLocation]:
        """All enabled locations (global + per-user) for the Beat schedule."""
        return (
            self.db.query(MonitoredLocation)
            .filter(MonitoredLocation.enabled.is_(True))
            .all()
        )

    def get_enabled_for_user(self, user_id: int) -> list[MonitoredLocation]:
        return (
            self.db.query(MonitoredLocation)
            .filter(
                MonitoredLocation.user_id == user_id,
                MonitoredLocation.enabled.is_(True),
            )
            .all()
        )

    def get_by_id(self, location_id: int) -> Optional[MonitoredLocation]:
        return self.db.get(MonitoredLocation, location_id)

    def create(
        self,
        *,
        name: str,
        latitude: float,
        longitude: float,
        radius: int = 1000,
        enabled: bool = True,
        user_id: Optional[int] = None,
    ) -> MonitoredLocation:
        location = MonitoredLocation(
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            enabled=enabled,
            user_id=user_id,
        )
        self.db.add(location)
        self.db.commit()
        self.db.refresh(location)
        return location

    def delete(self, location: MonitoredLocation) -> None:
        self.db.delete(location)
        self.db.commit()
