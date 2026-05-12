"""Health and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "libra-api", "version": __version__}


@router.get("/ready")
async def ready() -> dict[str, object]:
    settings = get_settings()
    return {
        "ok": True,
        "env": settings.env,
        "providers": {
            "openai_realtime": bool(settings.openai_api_key),
            "elevenlabs_openai": bool(
                settings.elevenlabs_api_key and settings.openai_api_key
            ),
        },
    }
