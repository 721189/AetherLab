from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project

# Allowed agent lifecycle states.
AGENT_STATUSES = ("active", "inactive", "paused", "archived")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # AI configuration.
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="gpt-4o",
    )

    system_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    temperature: Mapped[float] = mapped_column(
        default=0.7,
    )

    max_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    configuration: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Agent state.
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="inactive",
    )

    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # Relationships.
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="agents",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name={self.name}, project_id={self.project_id})>"