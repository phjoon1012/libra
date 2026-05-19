"""OpenAI Realtime voice provider.

Creates an ephemeral client secret via ``POST /v1/realtime/client_secrets``
(GA API) and returns it to the browser. The browser then performs the WebRTC
handshake at ``POST /v1/realtime/calls``. The long-lived ``OPENAI_API_KEY``
never leaves the server.

Reference: https://developers.openai.com/api/docs/guides/realtime-webrtc
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.tools import get_registry, register_builtin_tools
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

_OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
_OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"

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

        register_builtin_tools()
        _spotify_tool_names = [
            "spotify_search",
            "spotify_play",
            "spotify_pause",
            "spotify_resume",
            "spotify_skip",
            "spotify_now_playing",
        ]
        registry = get_registry()
        tools: list[object] = [
            t.to_openai_tool()
            for name in _spotify_tool_names
            if (t := registry.get(name)) is not None
        ]

        session_config: dict[str, object] = {
            "type": "realtime",
            "model": model,
            "audio": {"output": {"voice": voice}},
        }
        if ctx.augmented_instructions:
            session_config["instructions"] = ctx.augmented_instructions
        if tools:
            session_config["tools"] = tools
            session_config["tool_choice"] = "auto"

        payload = {"session": session_config}

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _OPENAI_CLIENT_SECRETS_URL, headers=headers, json=payload
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(
                    "OpenAI Realtime client_secret failed: status=%s body=%s payload=%s",
                    resp.status_code,
                    body,
                    payload,
                )
                raise OpenAIUpstreamError(resp.status_code, body)
            data = resp.json()

        # GA response: { "value": "ek_...", "expires_at": ..., "session": {...} }
        client_secret = data.get("value", "")
        if not client_secret:
            legacy = data.get("client_secret")
            if isinstance(legacy, dict):
                client_secret = legacy.get("value", "")

        session_obj = data.get("session") or {}
        resolved_model = (
            session_obj.get("model", model)
            if isinstance(session_obj, dict)
            else model
        )
        resolved_voice = voice
        if isinstance(session_obj, dict):
            audio = session_obj.get("audio") or {}
            if isinstance(audio, dict):
                output = audio.get("output") or {}
                if isinstance(output, dict) and output.get("voice"):
                    resolved_voice = str(output["voice"])

        expires_at = int(data.get("expires_at", 0))

        return OpenAIRealtimeSession(
            model=resolved_model,
            voice=resolved_voice,
            clientSecret=client_secret,
            expiresAt=expires_at,
            realtimeUrl=_OPENAI_REALTIME_CALLS_URL,
            sessionId=str(ctx.session_id),
        )
