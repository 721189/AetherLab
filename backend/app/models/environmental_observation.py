from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnvironmentalObservationRecord(Base):
    """Canonical, provider-independent observation persistence.

    This is the database counterpart of
    :class:`app.schemas.environmental.EnvironmentalObservation`: one row per
    variable measurement with full provenance. Unlike the legacy flattened
    ``environmental_readings`` table, adding NDVI / CH4 / LST / soil-moisture /
    chlorophyll requires NO schema change — they are just new rows.

    The legacy table is retained as a derived convenience snapshot for the
    existing API endpoints.
    """

    __tablename__ = "environmental_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Identity of the measurement
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    processing_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    variable: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)

    # Where / when
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("monitored_locations.id", ondelete="SET NULL"), nullable=True
    )

    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acquisition_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Scientific semantics & provenance
    averaging_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    resolution: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quality: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    quality_flags: Mapped[str | None] = mapped_column(
        String(1024), nullable=True  # JSON-encoded dict
    )

    # Explicit uncertainty model
    uncertainty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_completeness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Immutable provenance bundle (JSON): collection, scene_id, processing
    # algorithm/version, software version, CRS, AOI, cloud %, bands...
    provenance: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_env_obs_variable_time", "variable", "observed_at"),
        Index("ix_env_obs_source", "source"),
        Index("ix_env_obs_coords", "latitude", "longitude"),
    )

    def __repr__(self) -> str:
        return (
            f"<EnvironmentalObservationRecord(source={self.source!r}, "
            f"variable={self.variable!r}, value={self.value}, "
            f"unit={self.unit!r})>"
        )
