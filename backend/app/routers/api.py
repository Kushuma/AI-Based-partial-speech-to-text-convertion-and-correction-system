from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..database import get_session
from ..models.schemas import (
    DashboardResponse,
    HealthResponse,
    SessionSummary,
    TranscriptResponse,
    VocabularyCreate,
    VocabularyRead,
    WordConfidence,
)
from .. import state as state_module


router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()
logger = logging.getLogger(__name__)


def session_to_summary(record) -> SessionSummary:
    return SessionSummary(
        id=record.id,
        source=record.source,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        raw_transcript=record.raw_transcript,
        corrected_transcript=record.corrected_transcript,
        avg_confidence=record.avg_confidence,
        duration_seconds=record.duration_seconds,
        processing_ms=record.processing_ms,
        chunk_count=record.chunk_count,
        language=record.language,
    )


def _translate_processing_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    logger.exception("Unhandled audio processing error", exc_info=exc)
    return HTTPException(status_code=500, detail="Audio processing failed unexpectedly.")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        whisper_model=settings.whisper_model,
        correction_model=(
            f"{settings.gemini_model}+{settings.correction_model}"
            if settings.gemini_api_key
            else settings.correction_model
        ),
        cpu_only=settings.whisper_device == "cpu" and settings.correction_device == -1,
        gemini_enabled=bool(settings.gemini_api_key),
        gemini_model=settings.gemini_model if settings.gemini_api_key else None,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_session)) -> DashboardResponse:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")

    sessions = [session_to_summary(item) for item in state_module.state.sessions.list_sessions(db)]
    vocabulary = [
        VocabularyRead.model_validate(item, from_attributes=True)
        for item in state_module.state.sessions.list_vocabulary(db)
    ]
    parameters = [
        {"key": item.key, "value": item.value, "updated_at": item.updated_at}
        for item in state_module.state.sessions.list_parameters(db)
    ]
    return DashboardResponse(sessions=sessions, vocabulary=vocabulary, parameters=parameters)


@router.post("/sessions", response_model=SessionSummary)
def create_session(db: Session = Depends(get_session)) -> SessionSummary:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")

    record = state_module.state.sessions.create_session(db, source="live")
    return session_to_summary(record)


@router.post("/sessions/{session_id}/chunks", response_model=TranscriptResponse)
async def upload_chunk(
    session_id: str,
    audio: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> TranscriptResponse:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")

    record = state_module.state.sessions.get_session(db, session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found.")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio payload.")

    try:
        record, words = await run_in_threadpool(
            state_module.state.sessions.process_audio_bytes,
            db,
            record,
            audio_bytes,
            audio.filename,
            audio.content_type,
        )
    except Exception as exc:
        raise _translate_processing_error(exc) from exc
    return TranscriptResponse(
        session=session_to_summary(record),
        raw_transcript=record.raw_transcript,
        corrected_transcript=record.corrected_transcript,
        avg_confidence=record.avg_confidence,
        duration_seconds=record.duration_seconds,
        processing_ms=record.processing_ms,
        chunk_count=record.chunk_count,
        words=[WordConfidence(**item) for item in words],
    )


@router.post("/transcribe-file", response_model=TranscriptResponse)
async def transcribe_file(
    audio: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> TranscriptResponse:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")

    record = state_module.state.sessions.create_session(db, source="upload")
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    try:
        record, words = await run_in_threadpool(
            state_module.state.sessions.process_audio_bytes,
            db,
            record,
            audio_bytes,
            audio.filename,
            audio.content_type,
        )
    except Exception as exc:
        raise _translate_processing_error(exc) from exc
    return TranscriptResponse(
        session=session_to_summary(record),
        raw_transcript=record.raw_transcript,
        corrected_transcript=record.corrected_transcript,
        avg_confidence=record.avg_confidence,
        duration_seconds=record.duration_seconds,
        processing_ms=record.processing_ms,
        chunk_count=record.chunk_count,
        words=[WordConfidence(**item) for item in words],
    )


@router.get("/sessions/{session_id}", response_model=SessionSummary)
def get_session_details(session_id: str, db: Session = Depends(get_session)) -> SessionSummary:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")
    record = state_module.state.sessions.get_session(db, session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session_to_summary(record)


@router.post("/vocabulary", response_model=VocabularyRead)
def create_vocabulary(payload: VocabularyCreate, db: Session = Depends(get_session)) -> VocabularyRead:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")
    record = state_module.state.sessions.add_vocabulary(
        db,
        term=payload.term.strip(),
        pronunciation_hint=payload.pronunciation_hint.strip() if payload.pronunciation_hint else None,
        boost=payload.boost,
    )
    return VocabularyRead.model_validate(record, from_attributes=True)


@router.delete("/vocabulary/{vocab_id}")
def delete_vocabulary(vocab_id: int, db: Session = Depends(get_session)) -> dict[str, bool]:
    if state_module.state is None:
        raise HTTPException(status_code=503, detail="Application state is unavailable.")
    success = state_module.state.sessions.delete_vocabulary(db, vocab_id)
    if not success:
        raise HTTPException(status_code=404, detail="Vocabulary entry not found.")
    return {"ok": True}
