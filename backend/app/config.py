import os
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = ROOT_DIR / "backend" / "storage"


def _default_models_cache_dir() -> Path:
    if os.name != "nt":
        return STORAGE_DIR / "models"

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "speech-repair-studio" / "models"
    return Path.home() / "AppData" / "Local" / "speech-repair-studio" / "models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Speech Repair Studio"
    storage_dir: Path = STORAGE_DIR
    database_url: str = f"sqlite:///{(STORAGE_DIR / 'session.db').as_posix()}"
    whisper_model: str = "Systran/faster-whisper-large-v3"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    correction_model: str = "heuristic-repair-engine"
    correction_device: int = -1
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = Field(default=0.15, ge=0.0, le=1.0)
    gemini_timeout_seconds: int = Field(default=45, ge=5, le=300)
    gemini_low_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    gemini_low_word_probability: float = Field(default=0.58, ge=0.0, le=1.0)
    gemini_low_probability_ratio: float = Field(default=0.28, ge=0.0, le=1.0)
    gemini_max_audio_seconds: int = Field(default=45, ge=5, le=600)
    gemini_max_audio_mb: int = Field(default=15, ge=1, le=100)
    language_tool_lang: str = "en-US"
    language_code: str | None = "en"
    upload_sample_rate: int = 16000
    chunk_seconds: int = 4
    max_upload_mb: int = 50
    enable_language_tool: bool = False
    enable_composer: bool = False
    beam_size: int = 7
    best_of: int = 7
    compression_threshold: float = 2.2
    asr_recovery_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    asr_low_word_probability: float = Field(default=0.55, ge=0.0, le=1.0)
    ui_recent_sessions: int = Field(default=8, ge=1, le=50)
    local_langtool_path: Path = STORAGE_DIR / "langtool"
    models_cache_dir: Path = _default_models_cache_dir()
    audio_storage_dir: Path = STORAGE_DIR / "audio"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        settings.models_cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback_models_dir = Path(tempfile.gettempdir()) / "speech-repair-studio-models"
        fallback_models_dir.mkdir(parents=True, exist_ok=True)
        settings.models_cache_dir = fallback_models_dir
    settings.local_langtool_path.mkdir(parents=True, exist_ok=True)
    return settings
