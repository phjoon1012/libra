"""Health, readiness, and service-status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.core.db import get_db
from app.services.status import probe_all

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


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Per-service status (probed live, with a 60s upstream cache).

    Used by the dashboard status panel. See ``app.services.status``.
    """
    results = await probe_all(db)
    return {
        "services": {
            name: {"status": r.status, "detail": r.detail}
            for name, r in results.items()
        }
    }
