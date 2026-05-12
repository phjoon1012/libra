"""OpenAI Realtime voice provider.

Creates an ephemeral session via ``POST /v1/realtime/sessions`` and
returns the short-lived ``client_secret`` to the browser. The browser
then performs the WebRTC handshake directly with OpenAI using that
secret. The long-lived ``OPENAI_API_KEY`` never leaves the server.

Reference: https://platform.openai.com/docs/guides/realtime
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.schemas.voice import (
    OpenAIRealtimeSession,
    VoiceProviderDescriptor,
    VoiceSessionRequest,
)
from app.services.voice.base import (
    ProviderNotConfiguredError,
    SessionContext,
    VoiceProvider,
)

_OPENAI_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
_OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime"

logger = logging.getLogger(__name__)


class OpenAIUpstreamError(RuntimeError):
    """Raised when OpenAI rejects our session-mint request.

    Carries the upstream status + body so the route can translate it
    into a clean HTTP error for the browser.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"OpenAI {status}: {body}")
        self.status = status
        self.body = body


class OpenAIRealtimeProvider(VoiceProvider):
    @property
    def descriptor(self) -> VoiceProviderDescriptor:
        return VoiceProviderDescriptor(
            id="openai-realtime",
            label="OpenAI Realtime",
            description="Low-latency speech-to-speech via OpenAI Realtime over WebRTC.",
            status="ready",
        )

    async def create_session(
        self, req: VoiceSessionRequest, ctx: SessionContext
    ) -> OpenAIRealtimeSession:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ProviderNotConfiguredError(
                "OPENAI_API_KEY is not set. Add it to .env to enable OpenAI Realtime."
            )

        model = settings.openai_realtime_model
        voice = req.voice or settings.openai_realtime_voice

        payload: dict[str, object] = {"model": model, "voice": voice}
        if ctx.augmented_instructions:
            payload["instructions"] = ctx.augmented_instructions

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "realtime=v1",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _OPENAI_SESSIONS_URL, headers=headers, json=payload
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(
                    "OpenAI Realtime session mint failed: status=%s body=%s payload=%s",
                    resp.status_code,
                    body,
                    payload,
                )
                raise OpenAIUpstreamError(resp.status_code, body)
            data = resp.json()

        client_secret = data.get("client_secret", {})
        return OpenAIRealtimeSession(
            model=data.get("model", model),
            voice=data.get("voice", voice),
            clientSecret=client_secret.get("value", ""),
            expiresAt=int(client_secret.get("expires_at", 0)),
            realtimeUrl=_OPENAI_REALTIME_URL,
            sessionId=str(ctx.session_id),
        )
