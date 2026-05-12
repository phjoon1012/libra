"""Sanity checks: memory subsystem imports cleanly + schemas are stable.

These run without a DB / Redis connection, so they are safe in the
default CI environment.
"""

from __future__ import annotations

import uuid


def test_memory_service_module_loads() -> None:
    from app.services.memory import MemoryService, get_memory_service

    assert MemoryService is not None
    assert callable(get_memory_service)


def test_memory_schemas_round_trip() -> None:
    from app.schemas.memory import FactCreate, FactOut, MemorySearchRequest

    create = FactCreate(content="User likes oat milk", importance=4)
    assert create.content.startswith("User")
    assert create.importance == 4

    out = FactOut(
        id=uuid.uuid4(),
        user_id="default",
        content="hi",
        importance=3,
        source_session_id=None,
        created_at=__import__("datetime").datetime.now(),
        last_recalled_at=None,
        score=None,
    )
    # Default alias serialization.
    payload = out.model_dump(by_alias=True)
    assert "userId" in payload and "createdAt" in payload

    search = MemorySearchRequest(query="oat milk", topK=3)
    assert search.top_k == 3
    assert search.query == "oat milk"


def test_models_register_with_metadata() -> None:
    from app.models import Base, ChatSession, Fact

    table_names = set(Base.metadata.tables.keys())
    assert "sessions" in table_names
    assert "facts" in table_names
    # Sanity: the relationship columns we rely on exist.
    assert "embedding" in {c.name for c in Fact.__table__.columns}
    assert "ended_at" in {c.name for c in ChatSession.__table__.columns}
