"""Service status probes.

Used by ``GET /api/status`` to surface the health of upstream providers
and local infrastructure.

Upstream provider probes (OpenAI / ElevenLabs) are cached in-process for
60 seconds so the status panel can poll cheaply without burning quota.
Local probes (Postgres / Redis) are live on every call -- they're fast.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import session_scope
from app.core.redis import get_redis

ProbeStatus = Literal["connected", "not_configured", "error"]


@dataclass(slots=True)
class ProbeResult:
    status: ProbeStatus
    detail: str | None = None  # only set on "error"


# {key: (expires_at_epoch, result)}
_CACHE: dict[str, tuple[float, ProbeResult]] = {}
_CACHE_TTL = 60.0
_HTTP_TIMEOUT = 4.0


def _cached(key: str) -> ProbeResult | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    expires_at, result = entry
    if expires_at < time.time():
        _CACHE.pop(key, None)
        return None
    return result


def _store(key: str, result: ProbeResult) -> ProbeResult:
    _CACHE[key] = (time.time() + _CACHE_TTL, result)
    return result


async def probe_openai(settings: Settings) -> ProbeResult:
    if cached := _cached("openai"):
        return cached
    if not settings.openai_api_key:
        return _store("openai", ProbeResult("not_configured"))
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
        if resp.status_code == 200:
            return _store("openai", ProbeResult("connected"))
        if resp.status_code == 401:
            return _store("openai", ProbeResult("error", "invalid key"))
        return _store("openai", ProbeResult("error", f"HTTP {resp.status_code}"))
    except httpx.TimeoutException:
        return _store("openai", ProbeResult("error", "timeout"))
    except Exception as exc:  # noqa: BLE001
        return _store("openai", ProbeResult("error", str(exc)[:80]))


async def probe_elevenlabs(settings: Settings) -> ProbeResult:
    if cached := _cached("elevenlabs"):
        return cached
    if not settings.elevenlabs_api_key:
        return _store("elevenlabs", ProbeResult("not_configured"))
    # Use /v1/models: cheap, works with any TTS-scoped key. Avoid /v1/user
    # since many keys are minted without the user_read permission.
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/models",
                headers={"xi-api-key": settings.elevenlabs_api_key},
            )
        if resp.status_code == 200:
            return _store("elevenlabs", ProbeResult("connected"))
        if resp.status_code == 401:
            return _store("elevenlabs", ProbeResult("error", "invalid key"))
        return _store(
            "elevenlabs", ProbeResult("error", f"HTTP {resp.status_code}")
        )
    except httpx.TimeoutException:
        return _store("elevenlabs", ProbeResult("error", "timeout"))
    except Exception as exc:  # noqa: BLE001
        return _store("elevenlabs", ProbeResult("error", str(exc)[:80]))


async def probe_database(db: AsyncSession | None = None) -> ProbeResult:
    try:
        if db is not None:
            await db.execute(text("SELECT 1"))
        else:
            async with session_scope() as s:
                await s.execute(text("SELECT 1"))
        return ProbeResult("connected")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("error", str(exc)[:80])


async def probe_redis() -> ProbeResult:
    try:
        ok = await get_redis().ping()
        if ok:
            return ProbeResult("connected")
        return ProbeResult("error", "ping returned False")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult("error", str(exc)[:80])


async def probe_all(db: AsyncSession | None = None) -> dict[str, ProbeResult]:
    settings = get_settings()
    openai_t, eleven_t, db_t, redis_t = await asyncio.gather(
        probe_openai(settings),
        probe_elevenlabs(settings),
        probe_database(db),
        probe_redis(),
    )
    return {
        "openai": openai_t,
        "elevenlabs": eleven_t,
        "database": db_t,
        "redis": redis_t,
    }
