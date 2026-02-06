from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    programming_level: int = Field(default=3, ge=1, le=5)
    maths_level: int = Field(default=3, ge=1, le=5)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    id: UUID
    email: str
    programming_level: int
    maths_level: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserAssessment(BaseModel):
    programming_level: int = Field(ge=1, le=5)
    maths_level: int = Field(ge=1, le=5)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
