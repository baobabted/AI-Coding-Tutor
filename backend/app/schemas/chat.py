from datetime import datetime, date
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    session_id: UUID | None = None


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    hint_level_used: int | None = None
    problem_difficulty: int | None = None
    maths_difficulty: int | None = None
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
