from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Boolean, Float, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MonitoredLocation(Base):
    """A location whose environmental data is ingested periodically.

    Locations are user-owned: each user monitors their own set of places and
    the Celery Beat schedule fans out collection tasks per enabled row.
    ``user_id`` is nullable so operators can seed platform-wide (global)
    monitoring locations too.
    """

    __tablename__ = "monitored_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Search radius (metres) used for nearest-site provider queries.
    radius: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        # NOTE: text("true"), NOT func.true() -- func.true() renders as
        # `true()` which is invalid SQL on PostgreSQL (fine on SQLite, which
        # is exactly why the unit suite never caught it).
        server_default=text("true"),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def as_task_args(self) -> dict:
        """JSON-serialisable args for a Celery collect_location signature."""
        return {
            "lat": self.latitude,
            "lon": self.longitude,
            "location_name": self.name,
            "location_id": self.id,
        }

    def __repr__(self) -> str:
        return (
            f"<MonitoredLocation(id={self.id}, name={self.name!r}, "
            f"user_id={self.user_id}, enabled={self.enabled})>"
        )
