from datetime import datetime

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    # Optional agent whose stored config (model, temperature, max_tokens,
    # system_prompt) drives the LLM call for this message.
    agent_id: Optional[int] = None


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    created_at: datetime