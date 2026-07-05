from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str
    status: str = "processing"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    audio_path: str = ""
    processed_audio_path: str = ""
    raw_transcript: str = ""
    corrected_transcript: str = ""
    avg_confidence: float = 0.0
    duration_seconds: float = 0.0
    processing_ms: int = 0
    language: Optional[str] = None
    chunk_count: int = 0


class SessionRevision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    raw_transcript: str = ""
    corrected_transcript: str = ""
    avg_confidence: float = 0.0
    processing_ms: int = 0
    chunk_count: int = 0


class VocabularyEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    term: str = Field(index=True, unique=True)
    pronunciation_hint: Optional[str] = None
    boost: float = 1.0
    usage_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class AdaptiveParameter(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utc_now)

