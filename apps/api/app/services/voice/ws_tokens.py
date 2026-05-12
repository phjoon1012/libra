"""Single-use short-lived tokens for the voice WebSocket endpoints.

Why this exists:
  - POST /api/voice/session is CORS-protected and authenticated by the
    browser's same-origin policy in practice.
  - The WebSocket endpoint that follows is otherwise un-gated. Without a
    token, anyone on the same LAN (or a forwarded port) could open the
    WS directly and burn OpenAI / ElevenLabs credits.
  - A short-lived single-use token tied to the session POST shrinks that
    window to "the user is actively connecting right now".

This is intentionally in-memory only. v0.1 is single-user / local. When
we add proper auth in a later version we replace this with that.
"""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass

_TTL_SECONDS = 60.0
_MAX_INSTRUCTIONS = 8000  # raised: recall block can push baseline past 4k


@dataclass(slots=True)
class TokenData:
    expires_at: float
    instructions: str | None
    stability: float
    similarity_boost: float
    speed: float
    session_id: uuid.UUID
    user_id: str
    memory_enabled: bool


_REGISTRY: dict[str, TokenData] = {}


def mint(
    *,
    instructions: str | None,
    stability: float,
    similarity_boost: float,
    speed: float,
    session_id: uuid.UUID,
    user_id: str,
    memory_enabled: bool = True,
) -> str:
    """Create a single-use token. Returns the opaque token string."""
    _expire_old()
    token = secrets.token_urlsafe(24)
    if instructions is not None:
        instructions = instructions[:_MAX_INSTRUCTIONS]
    _REGISTRY[token] = TokenData(
        expires_at=time.time() + _TTL_SECONDS,
        instructions=instructions,
        stability=stability,
        similarity_boost=similarity_boost,
        speed=speed,
        session_id=session_id,
        user_id=user_id,
        memory_enabled=memory_enabled,
    )
    return token


def consume(token: str | None) -> TokenData | None:
    """Look up and remove the token. Returns None if missing/expired."""
    if not token:
        return None
    _expire_old()
    data = _REGISTRY.pop(token, None)
    if data is None or data.expires_at < time.time():
        return None
    return data


def _expire_old() -> None:
    now = time.time()
    stale = [tk for tk, d in _REGISTRY.items() if d.expires_at < now]
    for tk in stale:
        _REGISTRY.pop(tk, None)
