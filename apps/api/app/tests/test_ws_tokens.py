from __future__ import annotations

import time

from app.services.voice import ws_tokens


def test_mint_then_consume_succeeds_once() -> None:
    token = ws_tokens.mint(
        instructions="hello",
        stability=0.5,
        similarity_boost=0.6,
        speed=1.1,
    )
    assert isinstance(token, str) and len(token) > 16

    data = ws_tokens.consume(token)
    assert data is not None
    assert data.instructions == "hello"
    assert data.stability == 0.5
    assert data.similarity_boost == 0.6
    assert data.speed == 1.1

    # Second consume must fail — single-use semantics.
    assert ws_tokens.consume(token) is None


def test_consume_unknown_returns_none() -> None:
    assert ws_tokens.consume("not-a-real-token") is None
    assert ws_tokens.consume(None) is None


def test_expired_token_is_rejected() -> None:
    token = ws_tokens.mint(
        instructions=None, stability=0.4, similarity_boost=0.7, speed=1.0
    )
    # Force expiry by mutating the registry directly.
    ws_tokens._REGISTRY[token].expires_at = time.time() - 1.0  # noqa: SLF001
    assert ws_tokens.consume(token) is None
