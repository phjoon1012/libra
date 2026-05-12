"""Pydantic wire schemas for the memory API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FactCreate(BaseModel):
    """Body for manual fact insertion (POST /api/memory/facts)."""

    content: str = Field(..., min_length=1, max_length=2000)
    importance: int = Field(default=3, ge=1, le=5)
    user_id: str | None = Field(default=None, alias="userId")

    model_config = {"populate_by_name": True}


class FactOut(BaseModel):
    id: uuid.UUID
    user_id: str = Field(alias="userId")
    content: str
    importance: int
    source_session_id: uuid.UUID | None = Field(default=None, alias="sourceSessionId")
    created_at: datetime = Field(alias="createdAt")
    last_recalled_at: datetime | None = Field(default=None, alias="lastRecalledAt")
    # Filled by search endpoint; cosine similarity in [0, 2].
    score: float | None = Field(default=None)

    model_config = {"populate_by_name": True, "from_attributes": True}


class FactListResponse(BaseModel):
    facts: list[FactOut]
    total: int


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50, alias="topK")
    user_id: str | None = Field(default=None, alias="userId")

    model_config = {"populate_by_name": True}
