from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    created_at: datetime