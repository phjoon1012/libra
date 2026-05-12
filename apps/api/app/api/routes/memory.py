"""Memory placeholder route. Real implementation lands in v0.2."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def memory_status() -> dict[str, object]:
    # TODO(v0.2): replace with real short-term and long-term memory backends.
    return {
        "enabled": False,
        "short_term": "not_implemented",
        "long_term": "not_implemented",
        "note": "Persistent memory ships in v0.2.",
    }
