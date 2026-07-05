from __future__ import annotations

from dataclasses import dataclass

from .services.asr_service import ASRService
from .services.correction_service import CorrectionService
from .services.session_service import SessionService


@dataclass
class AppState:
    asr: ASRService
    correction: CorrectionService
    sessions: SessionService


state: AppState | None = None

