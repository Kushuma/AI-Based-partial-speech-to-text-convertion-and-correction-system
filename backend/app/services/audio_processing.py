from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import noisereduce as nr
import numpy as np
import soundfile as sf
from scipy import signal

from ..config import get_settings


settings = get_settings()


_AUDIO_MIME_TO_SUFFIX: dict[str, str] = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mp3": ".mp3",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/wave": ".wav",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
}


def _ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _audio_suffix(filename: str | None, content_type: str | None) -> str:
    if content_type:
        normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
        mapped_suffix = _AUDIO_MIME_TO_SUFFIX.get(normalized)
        if mapped_suffix:
            return mapped_suffix

    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix.startswith(".") and 1 < len(suffix) <= 10 and suffix.replace(".", "").isalnum():
            return suffix

    return ".bin"


def _trim_ffmpeg_error(stderr: str) -> str:
    message = stderr.strip().splitlines()[-1] if stderr else ""
    if not message:
        return "ffmpeg could not decode this audio payload."
    if len(message) > 240:
        return message[:240].rstrip() + "..."
    return message


def _mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    return audio.astype(np.float32)


def _trim_silence(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if audio.size == 0:
        return audio

    frame = max(1, int(sample_rate * 0.02))
    hop = max(1, int(sample_rate * 0.01))
    if len(audio) <= frame:
        return audio

    energies = []
    for start in range(0, len(audio) - frame + 1, hop):
        window = audio[start : start + frame]
        energies.append(float(np.sqrt(np.mean(window**2) + 1e-8)))

    if not energies:
        return audio

    envelope = np.asarray(energies, dtype=np.float32)
    threshold = max(0.008, float(np.percentile(envelope, 35)) * 0.55)
    voiced = np.where(envelope >= threshold)[0]
    if voiced.size == 0:
        return audio

    start = max(0, int(voiced[0] * hop) - int(sample_rate * 0.18))
    end = min(len(audio), int(voiced[-1] * hop + frame) + int(sample_rate * 0.22))
    return audio[start:end]


def _normalize_rms(audio: np.ndarray, target_rms: float = 0.12) -> np.ndarray:
    rms = float(np.sqrt(np.mean(audio**2) + 1e-8))
    if rms <= 0.0:
        return audio
    gain = np.clip(target_rms / rms, 1.0, 8.0)
    return (audio * gain).astype(np.float32)


def decode_upload(
    audio_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> tuple[np.ndarray, int]:
    source_path: Path | None = None
    target_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=_audio_suffix(filename, content_type), delete=False) as source:
            source.write(audio_bytes)
            source_path = Path(source.name)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as target:
            target_path = Path(target.name)

        ffmpeg_cmd = [
            _ffmpeg_path(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-ac",
            "1",
            "-ar",
            str(settings.upload_sample_rate),
            "-f",
            "wav",
            str(target_path),
        ]

        try:
            subprocess.run(
                ffmpeg_cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Audio decoding timed out. Please try a shorter recording.") from exc
        except subprocess.CalledProcessError as exc:
            media_hint = content_type or (source_path.suffix if source_path else "audio")
            detail = _trim_ffmpeg_error(exc.stderr or "")
            raise ValueError(f"Unable to decode uploaded {media_hint}: {detail}") from exc

        try:
            audio, sample_rate = sf.read(target_path, dtype="float32")
        except Exception as exc:
            raise ValueError("Decoded audio stream is invalid or unsupported.") from exc
        return _mono(audio), sample_rate
    finally:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        if target_path is not None:
            target_path.unlink(missing_ok=True)


def append_audio(master_path: Path, new_audio: np.ndarray, sample_rate: int) -> float:
    master_path.parent.mkdir(parents=True, exist_ok=True)
    if master_path.exists():
        existing_audio, existing_sr = sf.read(master_path, dtype="float32")
        if existing_sr != sample_rate:
            raise ValueError("Sample rate mismatch while appending audio.")
        combined = np.concatenate([existing_audio, new_audio])
    else:
        combined = new_audio

    sf.write(master_path, combined, sample_rate)
    return len(combined) / float(sample_rate)


def preprocess_audio(input_path: Path, output_path: Path) -> float:
    audio, sample_rate = sf.read(input_path, dtype="float32")
    audio = _mono(audio)
    audio = _trim_silence(audio, sample_rate)

    if audio.size == 0:
        audio = np.zeros(int(sample_rate * 0.25), dtype=np.float32)

    audio = signal.lfilter([1.0, -0.95], [1.0], audio).astype(np.float32)
    band_b, band_a = signal.butter(4, [70, 7600], btype="bandpass", fs=sample_rate)
    if len(audio) > max(len(band_a), len(band_b)) * 6:
        audio = signal.filtfilt(band_b, band_a, audio).astype(np.float32)
    else:
        audio = signal.lfilter(band_b, band_a, audio).astype(np.float32)
    audio = signal.wiener(audio, mysize=7).astype(np.float32)
    audio = _normalize_rms(audio)

    try:
        reduced = nr.reduce_noise(y=audio, sr=sample_rate, stationary=False, prop_decrease=0.9)
    except Exception:
        reduced = audio

    reduced = _normalize_rms(reduced.astype(np.float32), target_rms=0.14)
    reduced = np.tanh(reduced * 1.25).astype(np.float32)
    reduced = np.clip(reduced, -1.0, 1.0).astype(np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, reduced, sample_rate)
    return len(reduced) / float(sample_rate)
