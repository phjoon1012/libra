from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_list_providers_includes_both() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/voice/providers")
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()["providers"]}
        assert ids == {"openai-realtime", "elevenlabs-openai"}


def test_session_unknown_provider_returns_404() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/voice/session", json={"provider": "nope"})
        # Pydantic rejects the literal before the route runs.
        assert resp.status_code == 422


def test_session_elevenlabs_requires_keys() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/voice/session", json={"provider": "elevenlabs-openai"}
        )
        # In the test environment OPENAI_API_KEY / ELEVENLABS_API_KEY /
        # ELEVENLABS_VOICE_ID are unset, so the provider must refuse to
        # mint a session rather than silently returning bad config.
        assert resp.status_code == 503
        body = resp.json()
        assert "missing" in body["detail"].lower()
