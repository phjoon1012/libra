"""ElevenLabs + OpenAI voice provider.

This provider mints a session descriptor that points the browser at our
own WebSocket endpoint. The actual STT/LLM/TTS pipeline runs inside
``elevenlabs_openai_session.ElevenLabsOpenAISession`` so no provider
keys ever reach the browser.
"""

from __future__ import annotations

from urllib.parse import urlencode

from app.core.config import get_settings
from app.schemas.voice import (
    ElevenLabsOpenAISession,
    VoiceProviderDescriptor,
    VoiceSessionRequest,
    VoiceSettings,
)
from app.services.voice import ws_tokens
from app.services.voice.base import (
    ProviderNotConfiguredError,
    SessionContext,
    VoiceProvider,
)
from app.services.voice.elevenlabs_openai_session import (
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
)

_WS_PATH = "/api/voice/elevenlabs-openai/stream"


class ElevenLabsOpenAIProvider(VoiceProvider):
    @property
    def descriptor(self) -> VoiceProviderDescriptor:
        settings = get_settings()
        configured = bool(
            settings.openai_api_key
            and settings.elevenlabs_api_key
            and settings.elevenlabs_voice_id
        )
        return VoiceProviderDescriptor(
            id="elevenlabs-openai",
            label="ElevenLabs + OpenAI",
            description=(
                "Streaming OpenAI STT \u2192 OpenAI reasoning \u2192 ElevenLabs TTS."
            ),
            status="ready" if configured else "stub",
        )

    async def create_session(
        self, req: VoiceSessionRequest, ctx: SessionContext
    ) -> ElevenLabsOpenAISession:
        settings = get_settings()
        missing = [
            name
            for name, val in (
                ("OPENAI_API_KEY", settings.openai_api_key),
                ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key),
                ("ELEVENLABS_VOICE_ID", settings.elevenlabs_voice_id),
            )
            if not val
        ]
        if missing:
            raise ProviderNotConfiguredError(
                "ElevenLabs + OpenAI provider is missing: " + ", ".join(missing)
            )

        vs = req.voice_settings or VoiceSettings()
        token = ws_tokens.mint(
            instructions=ctx.augmented_instructions,
            stability=vs.stability,
            similarity_boost=vs.similarity_boost,
            speed=vs.speed,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            memory_enabled=ctx.memory_enabled,
        )

        # Browser supplies the absolute base; we only emit the relative
        # path + token. The frontend joins it with NEXT_PUBLIC_API_WS_BASE_URL.
        ws_url = f"{_WS_PATH}?{urlencode({'token': token})}"

        return ElevenLabsOpenAISession(
            wsUrl=ws_url,
            inputSampleRate=INPUT_SAMPLE_RATE,
            outputSampleRate=OUTPUT_SAMPLE_RATE,
            reasoningModel=settings.openai_reasoning_model,
            voiceId=settings.elevenlabs_voice_id or "",
            sessionId=str(ctx.session_id),
        )
