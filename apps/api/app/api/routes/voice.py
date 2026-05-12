"""Voice provider routes.

The browser does NOT receive long-lived provider API keys. Instead it
requests a short-lived session/config object from this endpoint, which
the appropriate provider service builds on the server side.

ElevenLabs + OpenAI additionally exposes a WebSocket endpoint that runs
the STT/LLM/TTS pipeline server-side.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.schemas.voice import (
    VoiceProviderListResponse,
    VoiceSessionRequest,
    VoiceSessionResponse,
)
from app.services.voice import ws_tokens
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
async def create_session(req: VoiceSessionRequest) -> VoiceSessionResponse:
    try:
        provider = get_provider(req.provider)
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    try:
        return await provider.create_session(req)
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
