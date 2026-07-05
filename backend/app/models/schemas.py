from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    whisper_model: str
    correction_model: str
    cpu_only: bool
    gemini_enabled: bool
    gemini_model: Optional[str]


class VocabularyCreate(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    pronunciation_hint: Optional[str] = Field(default=None, max_length=120)
    boost: float = Field(default=1.0, ge=0.5, le=5.0)


class VocabularyRead(BaseModel):
    id: int
    term: str
    pronunciation_hint: Optional[str]
    boost: float
    usage_count: int
    created_at: datetime


class AdaptiveParameterRead(BaseModel):
    key: str
    value: str
    updated_at: datetime


class WordConfidence(BaseModel):
    word: str
    start: float
    end: float
    probability: float


class SessionSummary(BaseModel):
    id: str
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
    raw_transcript: str
    corrected_transcript: str
    avg_confidence: float
    duration_seconds: float
    processing_ms: int
    chunk_count: int
    language: Optional[str]


class TranscriptResponse(BaseModel):
    session: SessionSummary
    raw_transcript: str
    corrected_transcript: str
    avg_confidence: float
    duration_seconds: float
    processing_ms: int
    chunk_count: int
    words: list[WordConfidence]


class DashboardResponse(BaseModel):
    sessions: list[SessionSummary]
    vocabulary: list[VocabularyRead]
    parameters: list[AdaptiveParameterRead]
