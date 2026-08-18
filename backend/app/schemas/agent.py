from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.agent import AGENT_STATUSES


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    model: str = Field(default="gpt-4o", max_length=100)
    system_prompt: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)
    configuration: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentCreate(AgentBase):
    status: Optional[str] = Field(default="inactive")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in AGENT_STATUSES:
            raise ValueError(
                f"status must be one of {AGENT_STATUSES}"
            )
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    model: Optional[str] = Field(None, max_length=100)
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)
    configuration: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    is_public: Optional[bool] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in AGENT_STATUSES:
            raise ValueError(
                f"status must be one of {AGENT_STATUSES}"
            )
        return v


class AgentResponse(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    is_public: bool
    created_at: datetime
    updated_at: datetime