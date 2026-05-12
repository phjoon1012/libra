"""Voice provider registry.

Single source of truth for which providers exist and how to look them up
by id. Routes import from here; they never reach into provider modules
directly.
"""

from __future__ import annotations

from app.schemas.voice import VoiceProviderDescriptor, VoiceProviderId
from app.services.voice.base import (
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    VoiceProvider,
)
from app.services.voice.elevenlabs_openai import ElevenLabsOpenAIProvider
from app.services.voice.openai_realtime import OpenAIRealtimeProvider

__all__ = [
    "ProviderNotConfiguredError",
    "ProviderNotFoundError",
    "get_provider",
    "list_providers",
]


_REGISTRY: dict[VoiceProviderId, VoiceProvider] = {
    "openai-realtime": OpenAIRealtimeProvider(),
    "elevenlabs-openai": ElevenLabsOpenAIProvider(),
}


def list_providers() -> list[VoiceProviderDescriptor]:
    return [p.descriptor for p in _REGISTRY.values()]


def get_provider(provider_id: VoiceProviderId) -> VoiceProvider:
    try:
        return _REGISTRY[provider_id]
    except KeyError as exc:
        raise ProviderNotFoundError(f"Unknown voice provider: {provider_id}") from exc
