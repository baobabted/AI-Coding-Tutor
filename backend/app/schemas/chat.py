from datetime import datetime, date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.upload import AttachmentOut


class ChatMessageIn(BaseModel):
    content: str = Field(default="", max_length=16000)
    session_id: UUID | None = None
    upload_ids: list[UUID] = Field(default_factory=list, max_length=5)


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    hint_level_used: int | None = None
    problem_difficulty: int | None = None
    maths_difficulty: int | None = None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    id: UUID
    session_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionListItem(BaseModel):
    id: UUID
    preview: str
    created_at: datetime


class TokenUsageOut(BaseModel):
    date: date
    input_tokens_used: int
    output_tokens_used: int
    daily_input_limit: int
    daily_output_limit: int
    usage_percentage: float
