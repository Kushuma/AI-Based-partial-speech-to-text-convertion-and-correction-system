from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers.api import router as api_router
from .services.asr_service import ASRService
from .services.correction_service import CorrectionService
from .services.session_service import SessionService
from .state import AppState
from . import state as state_module


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asr = ASRService()
    correction = CorrectionService()
    sessions = SessionService(asr=asr, correction=correction)
    state_module.state = AppState(asr=asr, correction=correction, sessions=sessions)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
