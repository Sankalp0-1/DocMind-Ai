"""
All Pydantic v2 schemas.
Keeps API contracts separate from ORM models (good practice).
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Documents ─────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: int
    original_name: str
    file_type: str
    file_size_bytes: int
    status: str
    duration_seconds: Optional[float] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    document_id: int
    question: str = Field(min_length=1, max_length=2000)
    stream: bool = False


class ChatSource(BaseModel):
    chunk_text: str
    page_or_timestamp: Optional[str] = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = []
    timestamp_hint: Optional[float] = None  # seconds — for audio/video play button


# ── Summary ───────────────────────────────────────────────────────────────────
class SummaryResponse(BaseModel):
    document_id: int
    summary: str
    key_topics: list[str] = []
    word_count: int


# ── Timestamps ────────────────────────────────────────────────────────────────
class TimestampEntry(BaseModel):
    topic: str
    start_seconds: float
    end_seconds: Optional[float] = None
    text_snippet: str


class TimestampResponse(BaseModel):
    document_id: int
    timestamps: list[TimestampEntry]
