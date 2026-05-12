from __future__ import annotations

import time
import uuid

from app.services.voice import ws_tokens


def _mint(**kw: object) -> str:
    return ws_tokens.mint(
        instructions=kw.get("instructions", "hello"),  # type: ignore[arg-type]
        stability=kw.get("stability", 0.5),  # type: ignore[arg-type]
        similarity_boost=kw.get("similarity_boost", 0.6),  # type: ignore[arg-type]
        speed=kw.get("speed", 1.1),  # type: ignore[arg-type]
        session_id=kw.get("session_id", uuid.uuid4()),  # type: ignore[arg-type]
        user_id=kw.get("user_id", "tester"),  # type: ignore[arg-type]
        memory_enabled=kw.get("memory_enabled", True),  # type: ignore[arg-type]
    )


def test_mint_then_consume_succeeds_once() -> None:
    sid = uuid.uuid4()
    token = _mint(session_id=sid, user_id="alice")
    assert isinstance(token, str) and len(token) > 16

    data = ws_tokens.consume(token)
    assert data is not None
    assert data.instructions == "hello"
    assert data.stability == 0.5
    assert data.similarity_boost == 0.6
    assert data.speed == 1.1
    assert data.session_id == sid
    assert data.user_id == "alice"
    assert data.memory_enabled is True

    # Second consume must fail — single-use semantics.
    assert ws_tokens.consume(token) is None


def test_consume_unknown_returns_none() -> None:
    assert ws_tokens.consume("not-a-real-token") is None
    assert ws_tokens.consume(None) is None


def test_expired_token_is_rejected() -> None:
    token = _mint(instructions=None, stability=0.4, similarity_boost=0.7, speed=1.0)
    # Force expiry by mutating the registry directly.
    ws_tokens._REGISTRY[token].expires_at = time.time() - 1.0  # noqa: SLF001
    assert ws_tokens.consume(token) is None


def test_memory_disabled_flag_is_preserved() -> None:
    token = _mint(memory_enabled=False)
    data = ws_tokens.consume(token)
    assert data is not None
    assert data.memory_enabled is False
