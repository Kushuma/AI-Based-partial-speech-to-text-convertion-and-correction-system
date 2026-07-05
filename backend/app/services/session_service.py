from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlmodel import Session, select

from ..config import get_settings
from ..models.db import AdaptiveParameter, SessionRecord, SessionRevision, VocabularyEntry
from .audio_processing import append_audio, decode_upload, preprocess_audio
from .asr_service import ASRService, TranscriptionResult
from .correction_service import CorrectionService


settings = get_settings()


class SessionService:
    def __init__(self, asr: ASRService, correction: CorrectionService) -> None:
        self.asr = asr
        self.correction = correction

    def create_session(self, db: Session, source: str) -> SessionRecord:
        session_id = uuid.uuid4().hex
        session_dir = settings.audio_storage_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        record = SessionRecord(
            id=session_id,
            source=source,
            status="ready",
            audio_path=str((session_dir / "master.wav").resolve()),
            processed_audio_path=str((session_dir / "processed.wav").resolve()),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_sessions(self, db: Session) -> list[SessionRecord]:
        statement = (
            select(SessionRecord)
            .order_by(SessionRecord.updated_at.desc())
            .limit(settings.ui_recent_sessions)
        )
        return list(db.exec(statement))

    def list_vocabulary(self, db: Session) -> list[VocabularyEntry]:
        return list(db.exec(select(VocabularyEntry).order_by(VocabularyEntry.term.asc())))

    def list_parameters(self, db: Session) -> list[AdaptiveParameter]:
        return list(db.exec(select(AdaptiveParameter).order_by(AdaptiveParameter.key.asc())))

    def get_session(self, db: Session, session_id: str) -> SessionRecord | None:
        return db.get(SessionRecord, session_id)

    def add_vocabulary(
        self,
        db: Session,
        term: str,
        pronunciation_hint: str | None,
        boost: float,
    ) -> VocabularyEntry:
        existing = db.exec(select(VocabularyEntry).where(VocabularyEntry.term == term)).first()
        if existing:
            existing.pronunciation_hint = pronunciation_hint
            existing.boost = boost
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing

        record = VocabularyEntry(term=term, pronunciation_hint=pronunciation_hint, boost=boost)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def delete_vocabulary(self, db: Session, vocab_id: int) -> bool:
        record = db.get(VocabularyEntry, vocab_id)
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True

    def _save_revision(self, db: Session, session_record: SessionRecord) -> None:
        revision = SessionRevision(
            session_id=session_record.id,
            raw_transcript=session_record.raw_transcript,
            corrected_transcript=session_record.corrected_transcript,
            avg_confidence=session_record.avg_confidence,
            processing_ms=session_record.processing_ms,
            chunk_count=session_record.chunk_count,
        )
        db.add(revision)

    def _set_param(self, db: Session, key: str, value: str) -> None:
        record = db.get(AdaptiveParameter, key)
        if record:
            record.value = value
            record.updated_at = datetime.now(timezone.utc)
            db.add(record)
        else:
            db.add(AdaptiveParameter(key=key, value=value))

    def _apply_transcription(
        self,
        db: Session,
        session_record: SessionRecord,
        transcription: TranscriptionResult,
        duration_seconds: float,
        processing_ms: int,
        processed_audio_path: Path,
    ) -> SessionRecord:
        vocabulary_terms = [entry.term for entry in self.list_vocabulary(db)]
        correction = self.correction.correct(
            transcription.raw_text,
            vocabulary_terms=vocabulary_terms,
            avg_confidence=transcription.avg_confidence,
            words=transcription.words,
            audio_path=processed_audio_path,
            duration_seconds=duration_seconds,
        )

        session_record.status = "ready"
        session_record.updated_at = datetime.now(timezone.utc)
        session_record.raw_transcript = transcription.raw_text
        session_record.corrected_transcript = correction.corrected_text
        session_record.avg_confidence = transcription.avg_confidence
        session_record.language = transcription.language
        session_record.duration_seconds = duration_seconds
        session_record.processing_ms = processing_ms
        session_record.chunk_count += 1

        db.add(session_record)
        self._save_revision(db, session_record)
        self._set_param(db, "last_average_confidence", f"{session_record.avg_confidence:.4f}")
        self._set_param(db, "last_chunk_count", str(session_record.chunk_count))
        self._set_param(db, "last_processing_ms", str(session_record.processing_ms))
        db.commit()
        db.refresh(session_record)
        return session_record

    def process_audio_bytes(
        self,
        db: Session,
        session_record: SessionRecord,
        audio_bytes: bytes,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> tuple[SessionRecord, list[dict]]:
        started = perf_counter()
        audio, sample_rate = decode_upload(audio_bytes, filename=filename, content_type=content_type)

        master_path = Path(session_record.audio_path)
        processed_path = Path(session_record.processed_audio_path)
        duration_seconds = append_audio(master_path, audio, sample_rate)
        preprocess_audio(master_path, processed_path)

        vocabulary_terms = [entry.term for entry in self.list_vocabulary(db)]
        transcription = self.asr.transcribe(processed_path, vocabulary_terms)

        record = self._apply_transcription(
            db=db,
            session_record=session_record,
            transcription=transcription,
            duration_seconds=duration_seconds,
            processing_ms=int((perf_counter() - started) * 1000),
            processed_audio_path=processed_path,
        )
        return record, transcription.words
