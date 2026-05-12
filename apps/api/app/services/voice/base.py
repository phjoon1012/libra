"""Voice provider interface.

Every provider implements this contract. Provider-specific networking,
keys, and SDKs live behind these methods so routes and the frontend stay
provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.voice import (
    VoiceProviderDescriptor,
    VoiceSessionRequest,
    VoiceSessionResponse,
)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a provider is requested but its credentials are missing."""


class ProviderNotFoundError(LookupError):
    """Raised when a provider id is unknown to the registry."""


class VoiceProvider(ABC):
    """Abstract voice provider."""

    @property
    @abstractmethod
    def descriptor(self) -> VoiceProviderDescriptor:
        """Return the user-facing description of this provider."""

    @abstractmethod
    async def create_session(
        self, req: VoiceSessionRequest
    ) -> VoiceSessionResponse:
        """Create the short-lived session/config the browser will use."""
