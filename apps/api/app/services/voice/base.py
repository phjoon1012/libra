"""Voice provider interface.

Every provider implements this contract. Provider-specific networking,
keys, and SDKs live behind these methods so routes and the frontend stay
provider-agnostic.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.voice import (
    VoiceProviderDescriptor,
    VoiceSessionRequest,
    VoiceSessionResponse,
)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a provider is requested but its credentials are missing."""


class ProviderNotFoundError(LookupError):
    """Raised when a provider id is unknown to the registry."""


@dataclass(slots=True)
class SessionContext:
    """Per-session values resolved by the backend before calling a provider.

    Kept off the wire request schema so the browser cannot forge them.
    """

    session_id: uuid.UUID
    user_id: str
    # ``req.instructions`` already augmented with the recall context
    # block at session start. Providers should use this verbatim.
    augmented_instructions: str | None
    memory_enabled: bool = True


class VoiceProvider(ABC):
    """Abstract voice provider."""

    @property
    @abstractmethod
    def descriptor(self) -> VoiceProviderDescriptor:
        """Return the user-facing description of this provider."""

    @abstractmethod
    async def create_session(
        self, req: VoiceSessionRequest, ctx: SessionContext
    ) -> VoiceSessionResponse:
        """Create the short-lived session/config the browser will use."""
