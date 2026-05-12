"""Pydantic schemas for voice provider endpoints.

Wire shape matches ``packages/shared-types/src/voice.ts``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VoiceProviderId = Literal["openai-realtime", "elevenlabs-openai"]


class VoiceProviderDescriptor(BaseModel):
    id: VoiceProviderId
    label: str
    description: str
    status: Literal["ready", "stub"]


class VoiceProviderListResponse(BaseModel):
    providers: list[VoiceProviderDescriptor]


class VoiceSettings(BaseModel):
    """ElevenLabs voice tunables. Ignored by other providers."""

    stability: float = Field(default=0.45, ge=0.0, le=1.0)
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0, alias="similarityBoost")
    speed: float = Field(default=1.0, ge=0.7, le=1.2)

    model_config = {"populate_by_name": True}


class VoiceSessionRequest(BaseModel):
    provider: VoiceProviderId = Field(
        ..., description="Which voice provider to start a session with."
    )
    voice: str | None = Field(
        default=None, description="Optional voice override (provider-specific)."
    )
    instructions: str | None = Field(
        default=None, description="Optional system-prompt override."
    )
    voice_settings: VoiceSettings | None = Field(
        default=None,
        alias="voiceSettings",
        description="ElevenLabs voice tunables.",
    )
    memory_enabled: bool = Field(
        default=True,
        alias="memoryEnabled",
        description=(
            "When false: skip recall on connect, skip turn capture, "
            "and skip end-of-session distillation."
        ),
    )

    model_config = {"populate_by_name": True}


class OpenAIRealtimeSession(BaseModel):
    provider: Literal["openai-realtime"] = "openai-realtime"
    model: str
    voice: str
    client_secret: str = Field(..., alias="clientSecret")
    expires_at: int = Field(..., alias="expiresAt")
    realtime_url: str = Field(..., alias="realtimeUrl")
    session_id: str = Field(..., alias="sessionId")

    model_config = {"populate_by_name": True}


class ElevenLabsOpenAISession(BaseModel):
    provider: Literal["elevenlabs-openai"] = "elevenlabs-openai"
    ws_url: str = Field(..., alias="wsUrl")
    input_sample_rate: int = Field(..., alias="inputSampleRate")
    output_sample_rate: int = Field(..., alias="outputSampleRate")
    reasoning_model: str = Field(..., alias="reasoningModel")
    voice_id: str = Field(..., alias="voiceId")
    session_id: str = Field(..., alias="sessionId")

    model_config = {"populate_by_name": True}


VoiceSessionResponse = OpenAIRealtimeSession | ElevenLabsOpenAISession


class TurnCapture(BaseModel):
    """Body for POST /api/voice/session/{id}/turn.

    Used by clients that orchestrate the turn themselves (currently
    only the OpenAI Realtime browser client; the ElevenLabs+OpenAI
    pipeline records turns server-side).
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
