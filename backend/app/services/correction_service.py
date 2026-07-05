from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from ..config import get_settings


settings = get_settings()

FILLER_PATTERNS = [
    r"\bum\b",
    r"\buh\b",
    r"\bhum\b",
    r"\bhmm+\b",
    r"\ber\b",
    r"\bah\b",
    r"\byou know\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bI mean\b",
]


@dataclass
class CorrectionResult:
    corrected_text: str
    normalized_text: str


class GeminiRepairPayload(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=4000)
    completion_applied: bool = False
    noise_ignored: bool = False


class CorrectionService:
    def __init__(self) -> None:
        self.tool = None
        self.client = None
        self.genai_types = None

        if settings.enable_language_tool:
            try:
                import language_tool_python

                self.tool = language_tool_python.LanguageTool(
                    settings.language_tool_lang,
                    config={"cacheSize": 1000, "pipelineCaching": True},
                )
            except Exception:
                self.tool = None

        if settings.gemini_api_key:
            try:
                from google import genai
                from google.genai import types

                self.client = genai.Client(api_key=settings.gemini_api_key)
                self.genai_types = types
            except Exception:
                self.client = None
                self.genai_types = None

    def _normalize(self, text: str) -> str:
        cleaned = text
        for pattern in FILLER_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bneed clear and complete\b", "need a clear and complete", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bcreate clear and complete\b", "create a clear and complete", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bfrom broken speech\b", "from broken speech", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s([,.!?;:])", r"\1", cleaned)
        cleaned = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", cleaned)
        cleaned = cleaned.strip(" ,")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def _language_tool(self, text: str) -> str:
        if not self.tool or not text:
            return text
        try:
            return self.tool.correct(text)
        except Exception:
            return text

    def _apply_vocabulary_bias(self, text: str, vocabulary_terms: list[str]) -> str:
        updated = text
        lowered_words = re.findall(r"\b[\w'-]+\b", text.lower())

        for term in vocabulary_terms:
            lowered_term = term.lower()
            if lowered_term in text.lower():
                continue
            best = max((fuzz.ratio(lowered_term, word) for word in lowered_words), default=0)
            if best >= 88:
                updated = re.sub(
                    pattern=r"\b[\w'-]+\b",
                    repl=lambda match: term
                    if fuzz.ratio(lowered_term, match.group(0).lower()) >= 88
                    else match.group(0),
                    string=updated,
                    count=1,
                )
        return updated

    def _looks_incomplete(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if stripped.endswith((".", "!", "?")):
            return False
        return bool(
            re.search(
                r"\b(and|but|so|because|if|when|while|with|for|to|of|in|on|at|from|that|which|who|is|are|was|were|be|been|being|have|has|had|do|does|did|can|could|would|should|will|shall|may|might|must)$",
                stripped,
                flags=re.IGNORECASE,
            )
        ) or len(stripped.split()) <= 6

    def _low_probability_ratio(self, words: list[dict[str, Any]] | None) -> float:
        if not words:
            return 1.0
        low_probability = sum(
            1
            for word in words
            if float(word.get("probability", 0.0) or 0.0) < settings.gemini_low_word_probability
        )
        return low_probability / float(len(words))

    def _should_use_gemini(
        self,
        raw_text: str,
        normalized_text: str,
        avg_confidence: float,
        words: list[dict[str, Any]] | None,
    ) -> bool:
        if not self.client or not raw_text.strip():
            return False
        if avg_confidence < settings.gemini_low_confidence_threshold:
            return True
        if self._low_probability_ratio(words) >= settings.gemini_low_probability_ratio:
            return True
        if self._looks_incomplete(raw_text):
            return True
        return normalized_text.strip() == raw_text.strip() and avg_confidence < 0.88

    def _gemini_prompt(
        self,
        raw_text: str,
        normalized_text: str,
        vocabulary_terms: list[str],
        avg_confidence: float,
        words: list[dict[str, Any]] | None,
    ) -> str:
        low_confidence_words = [
            word["word"]
            for word in (words or [])
            if float(word.get("probability", 0.0) or 0.0) < settings.gemini_low_word_probability
        ][:20]
        vocabulary_hint = ", ".join(vocabulary_terms[:60]) if vocabulary_terms else "None"
        low_confidence_hint = ", ".join(low_confidence_words) if low_confidence_words else "None"

        return (
            "You repair noisy speech transcripts.\n"
            "Return JSON only.\n"
            "Rules:\n"
            "- Ignore background noise, hum, fan noise, traffic, clicks, and non-speech.\n"
            "- Preserve the speaker's meaning.\n"
            "- Correct grammar, casing, punctuation, and minor wording errors.\n"
            "- Complete an unfinished sentence only when the intended continuation is strongly implied.\n"
            "- Do not invent names, numbers, or facts.\n"
            "- Prefer these domain terms when plausible: "
            f"{vocabulary_hint}.\n"
            f"ASR confidence: {avg_confidence:.3f}.\n"
            f"Low-confidence words: {low_confidence_hint}.\n"
            "Current ASR transcript:\n"
            f"{raw_text or '[empty]'}\n\n"
            "Heuristic cleaned draft:\n"
            f"{normalized_text or '[empty]'}\n\n"
            "Produce one polished grammatical transcript string."
        )

    def _call_gemini(
        self,
        raw_text: str,
        normalized_text: str,
        vocabulary_terms: list[str],
        avg_confidence: float,
        words: list[dict[str, Any]] | None,
        audio_path: Path | None,
        duration_seconds: float,
    ) -> str | None:
        if not self.client or not self.genai_types:
            return None

        prompt = self._gemini_prompt(
            raw_text=raw_text,
            normalized_text=normalized_text,
            vocabulary_terms=vocabulary_terms,
            avg_confidence=avg_confidence,
            words=words,
        )

        contents: list[Any] = [prompt]
        uploaded_audio = None
        if (
            audio_path
            and audio_path.exists()
            and duration_seconds <= settings.gemini_max_audio_seconds
            and audio_path.stat().st_size <= settings.gemini_max_audio_mb * 1024 * 1024
        ):
            try:
                uploaded_audio = self.client.files.upload(file=str(audio_path))
                contents = [uploaded_audio, prompt]
            except Exception:
                uploaded_audio = None
                contents = [prompt]

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=self.genai_types.GenerateContentConfig(
                    temperature=settings.gemini_temperature,
                    response_mime_type="application/json",
                    response_schema=GeminiRepairPayload,
                ),
            )
            payload = getattr(response, "parsed", None)
            if payload is None:
                payload = GeminiRepairPayload.model_validate_json(response.text)
            corrected_text = payload.corrected_text.strip()
            return corrected_text or None
        except Exception:
            return None
        finally:
            if uploaded_audio is not None:
                delete_file = getattr(self.client.files, "delete", None)
                if callable(delete_file):
                    try:
                        delete_file(name=uploaded_audio.name)
                    except Exception:
                        pass

    def _choose_candidate(self, raw_text: str, baseline: str, candidate: str, avg_confidence: float) -> str:
        if not candidate:
            return baseline

        overlap = fuzz.token_set_ratio(baseline, candidate) / 100.0 if baseline else 1.0
        raw_overlap = fuzz.token_set_ratio(raw_text, candidate) / 100.0 if raw_text else 1.0
        if avg_confidence >= 0.8 and overlap < 0.34:
            return baseline
        if avg_confidence >= 0.72 and raw_overlap < 0.24:
            return baseline
        if len(candidate.split()) > max(5, len(baseline.split()) + 14):
            return baseline
        return candidate

    def correct(
        self,
        raw_text: str,
        vocabulary_terms: list[str],
        avg_confidence: float,
        words: list[dict[str, Any]] | None = None,
        audio_path: Path | None = None,
        duration_seconds: float = 0.0,
    ) -> CorrectionResult:
        normalized = self._language_tool(self._normalize(raw_text))
        candidate = self._apply_vocabulary_bias(self._language_tool(normalized), vocabulary_terms)

        if self._should_use_gemini(raw_text, candidate, avg_confidence, words):
            gemini_candidate = self._call_gemini(
                raw_text=raw_text,
                normalized_text=candidate,
                vocabulary_terms=vocabulary_terms,
                avg_confidence=avg_confidence,
                words=words,
                audio_path=audio_path,
                duration_seconds=duration_seconds,
            )
            if gemini_candidate:
                gemini_candidate = self._apply_vocabulary_bias(
                    self._language_tool(self._normalize(gemini_candidate)),
                    vocabulary_terms,
                )
                candidate = self._choose_candidate(raw_text, candidate, gemini_candidate, avg_confidence)

        candidate = self._apply_vocabulary_bias(candidate, vocabulary_terms)

        overlap = fuzz.token_set_ratio(raw_text, candidate) / 100.0 if raw_text else 1.0
        if not candidate:
            candidate = normalized
        elif avg_confidence >= 0.55 and overlap < 0.42:
            candidate = normalized
        elif len(candidate.split()) > max(3, len(raw_text.split()) * 2):
            candidate = normalized

        return CorrectionResult(corrected_text=candidate, normalized_text=normalized)


