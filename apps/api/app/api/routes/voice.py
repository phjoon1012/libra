"""Voice provider routes.

The browser does NOT receive long-lived provider API keys. Instead it
requests a short-lived session/config object from this endpoint, which
the appropriate provider service builds on the server side.

ElevenLabs + OpenAI additionally exposes a WebSocket endpoint that runs
the STT/LLM/TTS pipeline server-side.

This module also exposes the memory-bound session lifecycle hooks
(/turn, /end) used by the OpenAI Realtime browser client to capture
turns and trigger end-of-session distillation.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.voice import (
    TurnCapture,
    VoiceProviderListResponse,
    VoiceSessionRequest,
    VoiceSessionResponse,
)
from app.services.memory import get_memory_service
from app.services.voice import ws_tokens
from app.services.voice.base import SessionContext
from app.services.voice.elevenlabs_openai_session import ElevenLabsOpenAISession
from app.services.voice.openai_realtime import OpenAIUpstreamError
from app.services.voice.registry import (
    get_provider,
    list_providers,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers", response_model=VoiceProviderListResponse)
async def providers() -> VoiceProviderListResponse:
    return VoiceProviderListResponse(providers=list_providers())


@router.post("/session", response_model=VoiceSessionResponse)
async def create_session(
    req: VoiceSessionRequest, db: AsyncSession = Depends(get_db)
) -> VoiceSessionResponse:
    try:
        provider = get_provider(req.provider)
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    settings = get_settings()
    user_id = settings.memory_default_user_id

    svc = get_memory_service(db)
    # We always create a session row so end/turn endpoints stay valid;
    # the ``memory_enabled`` flag instead gates *use* downstream.
    session_id = await svc.start_session(user_id=user_id, provider=req.provider)

    # When memory is enabled, prepend a baseline recall block to the
    # system prompt so the assistant has cross-session user awareness
    # from the first utterance. Per-turn semantic recall happens later
    # in the orchestrator (EL+OAI path only).
    base_instructions = req.instructions
    augmented = base_instructions
    if req.memory_enabled:
        facts, _total = await svc.list_facts(user_id=user_id, limit=8, offset=0)
        if facts:
            block = (
                "What you remember about the user from prior conversations "
                "(use sparingly and only when clearly relevant):\n"
                + "\n".join(f"- {f.content}" for f in facts)
            )
            augmented = (
                f"{base_instructions}\n\n{block}" if base_instructions else block
            )

    ctx = SessionContext(
        session_id=session_id,
        user_id=user_id,
        augmented_instructions=augmented,
        memory_enabled=req.memory_enabled,
    )

    try:
        return await provider.create_session(req, ctx)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except OpenAIUpstreamError as exc:
        # Upstream rejected our request (bad model, no quota, etc.).
        # Return 502 with the upstream body so the UI can show a useful
        # message instead of a CORS-stripped 500.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI Realtime upstream error ({exc.status}): {exc.body}",
        ) from exc


@router.post("/session/{session_id}/turn", status_code=status.HTTP_204_NO_CONTENT)
async def capture_turn(
    session_id: uuid.UUID,
    payload: TurnCapture,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Record one turn into short-term memory.

    Used by clients that orchestrate the turn themselves (OpenAI
    Realtime via the browser). The EL+OAI server-side pipeline records
    turns directly without this endpoint.
    """
    svc = get_memory_service(db)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await svc.record_turn(
        session_id=session_id, role=payload.role, content=payload.content
    )


@router.post("/session/{session_id}/end", status_code=status.HTTP_200_OK)
async def end_session(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Mark a session as ended and schedule distillation in the background."""
    svc = get_memory_service(db)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await svc.end_session(session_id)
    # ``schedule_distill`` fires-and-forgets a background task with its
    # own DB session; safe to call before our request transaction commits.
    await svc.schedule_distill(session_id=session_id, user_id=chat.user_id)
    return {"status": "scheduled"}


@router.websocket("/elevenlabs-openai/stream")
async def elevenlabs_openai_stream(ws: WebSocket) -> None:
    """Browser ↔ backend full-duplex bridge for the ElevenLabs + OpenAI pipeline.

    Binary frames: 16-bit LE mono PCM at 16 kHz.
      - Up:   browser microphone capture.
      - Down: ElevenLabs TTS audio.

    Text frames (JSON): control + transcript events in both directions.

    Auth: the browser must present a single-use token minted by
    POST /api/voice/session. Tokens expire after 60 seconds and are
    invalidated on first consumption.
    """
    token = ws.query_params.get("token")
    data = ws_tokens.consume(token)
    if data is None:
        # 1008 = Policy Violation; closes the handshake cleanly.
        await ws.close(code=1008, reason="invalid or expired token")
        return

    await ws.accept()
    settings = get_settings()
    session = ElevenLabsOpenAISession(
        ws,
        settings,
        data.instructions,
        voice_stability=data.stability,
        voice_similarity_boost=data.similarity_boost,
        voice_speed=data.speed,
        session_id=data.session_id,
        user_id=data.user_id,
        memory_enabled=data.memory_enabled,
    )
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("elevenlabs-openai session crashed")
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass
