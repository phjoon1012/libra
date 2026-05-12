from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_ok() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "libra-api"


def test_ready_includes_provider_flags() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert "providers" in body
        assert "openai_realtime" in body["providers"]
        assert "elevenlabs_openai" in body["providers"]
