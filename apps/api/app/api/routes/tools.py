"""Tools placeholder route. Real implementation lands in v0.3."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def tools_status() -> dict[str, object]:
    # TODO(v0.3+): expose discovered tools and their permission requirements.
    return {
        "enabled": False,
        "tools": [],
        "note": "Tool execution ships in v0.3 behind an explicit permission layer.",
    }
