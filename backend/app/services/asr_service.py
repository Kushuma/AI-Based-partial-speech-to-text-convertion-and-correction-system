from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from threading import Lock

from faster_whisper import WhisperModel

from ..config import get_settings


settings = get_settings()


@dataclass
class TranscriptionResult:
    raw_text: str
    avg_confidence: float
    language: str | None
    words: list[dict]


class ASRService:
    def __init__(self) -> None:
        self._model: WhisperModel | None = None
        self._model_lock = Lock()

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    try:
                        self._model = WhisperModel(
                            settings.whisper_model,
                            device=settings.whisper_device,
                            compute_type=settings.whisper_compute_type,
                            download_root=str(settings.models_cache_dir),
                        )
                    except FileNotFoundError as exc:
                        raise RuntimeError(
                            "Whisper model cache path is unavailable. Set APP_MODELS_CACHE_DIR to a short path "
                            "such as C:\\asr-models and restart the backend."
                        ) from exc
        return self._model

    def _collect_result(self, segments, info) -> TranscriptionResult:
        lines: list[str] = []
        words: list[dict] = []
        probabilities: list[float] = []

        for segment in segments:
            lines.append(segment.text.strip())
            for word in segment.words or []:
                probability = float(getattr(word, 'probability', 0.0) or 0.0)
                probabilities.append(probability)
                words.append(
                    {
                        'word': word.word.strip(),
                        'start': float(word.start),
                        'end': float(word.end),
                        'probability': probability,
                    }
                )

        raw_text = ' '.join(part for part in lines if part).strip()
        avg_confidence = sum(probabilities) / len(probabilities) if probabilities else 0.0
        return TranscriptionResult(
            raw_text=raw_text,
            avg_confidence=avg_confidence,
            language=getattr(info, 'language', None),
            words=words,
        )

    def _run_pass(self, audio_path: Path, vocabulary_terms: list[str], recovery_mode: bool) -> TranscriptionResult:
        hotwords = ', '.join(vocabulary_terms[:80]) if vocabulary_terms else None
        initial_prompt = (
            'Recover softly spoken English speech accurately. Ignore background noise, hum, traffic, clicks, and other non-speech sounds.'
        )
        if vocabulary_terms:
            initial_prompt += ' Prefer these domain terms when acoustically plausible: ' + ', '.join(
                vocabulary_terms[:80]
            )

        kwargs = {
            'language': settings.language_code,
            'beam_size': settings.beam_size,
            'best_of': settings.best_of,
            'vad_filter': True,
            'vad_parameters': {
                'min_silence_duration_ms': 380,
                'speech_pad_ms': 420,
            },
            'word_timestamps': True,
            'condition_on_previous_text': True,
            'initial_prompt': initial_prompt,
            'compression_ratio_threshold': settings.compression_threshold,
            'hallucination_silence_threshold': 1.2,
            'hotwords': hotwords,
        }

        if recovery_mode:
            kwargs.update(
                {
                    'beam_size': max(settings.beam_size, 9),
                    'best_of': max(settings.best_of, 9),
                    'condition_on_previous_text': False,
                    'initial_prompt': initial_prompt,
                    'temperature': [0.0, 0.2, 0.4],
                    'log_prob_threshold': -1.5,
                    'no_speech_threshold': 0.35,
                    'compression_ratio_threshold': max(settings.compression_threshold, 2.5),
                }
            )

        segments, info = self._get_model().transcribe(
            str(audio_path),
            **kwargs,
        )
        return self._collect_result(segments, info)

    def _low_probability_ratio(self, words: list[dict]) -> float:
        if not words:
            return 1.0
        low = sum(1 for word in words if float(word.get('probability', 0.0)) < settings.asr_low_word_probability)
        return low / float(len(words))

    def _looks_incomplete(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        if stripped[-1] in '.!?':
            return False
        return bool(
            re.search(
                r'\b(and|but|so|because|if|when|while|with|for|to|of|in|on|at|from|that|which|who|is|are|was|were|be|been|being|have|has|had|do|does|did|can|could|would|should|will|shall|may|might|must)$',
                stripped,
                flags=re.IGNORECASE,
            )
        ) or len(stripped.split()) <= 6

    def _needs_recovery(self, result: TranscriptionResult) -> bool:
        return (
            not result.raw_text
            or result.avg_confidence < settings.asr_recovery_confidence_threshold
            or self._low_probability_ratio(result.words) >= 0.34
            or self._looks_incomplete(result.raw_text)
        )

    def _result_score(self, result: TranscriptionResult) -> float:
        text = result.raw_text.strip()
        if not text:
            return -1.0
        punctuation_bonus = 0.06 if text.endswith(('.', '!', '?')) else 0.0
        length_bonus = min(len(text.split()), 18) / 18.0 * 0.08
        low_probability_penalty = self._low_probability_ratio(result.words) * 0.15
        return result.avg_confidence + punctuation_bonus + length_bonus - low_probability_penalty

    def transcribe(self, audio_path: Path, vocabulary_terms: list[str]) -> TranscriptionResult:
        primary = self._run_pass(audio_path, vocabulary_terms, recovery_mode=False)
        if not self._needs_recovery(primary):
            return primary

        fallback = self._run_pass(audio_path, vocabulary_terms, recovery_mode=True)
        return fallback if self._result_score(fallback) >= self._result_score(primary) else primary
