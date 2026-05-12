"""Memory API.

Routes are intentionally thin: they validate input, call into the
``MemoryService``, and map results to wire schemas.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.models.memory import Fact
from app.schemas.memory import (
    FactCreate,
    FactListResponse,
    FactOut,
    MemorySearchRequest,
)
from app.services.memory import get_memory_service

router = APIRouter()


def _resolve_user(user_id: str | None) -> str:
    return user_id or get_settings().memory_default_user_id


def _to_out(fact: Fact, score: float | None = None) -> FactOut:
    return FactOut(
        id=fact.id,
        user_id=fact.user_id,
        content=fact.content,
        importance=fact.importance,
        source_session_id=fact.source_session_id,
        created_at=fact.created_at,
        last_recalled_at=fact.last_recalled_at,
        score=score,
    )


@router.get("/status")
async def memory_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "enabled": True,
        "short_term": "redis",
        "long_term": "postgres+pgvector",
        "embedding_model": settings.openai_embedding_model,
        "recall_top_k": settings.memory_recall_top_k,
    }


@router.get("/facts", response_model=FactListResponse)
async def list_facts(
    user_id: str | None = Query(default=None, alias="userId"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FactListResponse:
    svc = get_memory_service(db)
    facts, total = await svc.list_facts(
        user_id=_resolve_user(user_id), limit=limit, offset=offset
    )
    return FactListResponse(facts=[_to_out(f) for f in facts], total=total)


@router.post(
    "/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED
)
async def create_fact(
    payload: FactCreate, db: AsyncSession = Depends(get_db)
) -> FactOut:
    svc = get_memory_service(db)
    fact = await svc.add_fact(
        user_id=_resolve_user(payload.user_id),
        content=payload.content,
        importance=payload.importance,
    )
    return _to_out(fact)


@router.post("/search", response_model=list[FactOut])
async def search_facts(
    payload: MemorySearchRequest, db: AsyncSession = Depends(get_db)
) -> list[FactOut]:
    svc = get_memory_service(db)
    hits = await svc.search_facts(
        user_id=_resolve_user(payload.user_id),
        query=payload.query,
        top_k=payload.top_k,
    )
    return [_to_out(f, score=score) for f, score in hits]


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(
    fact_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = get_memory_service(db)
    deleted = await svc.delete_fact(fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")


@router.delete("/facts", status_code=status.HTTP_200_OK)
async def delete_all_facts(
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    svc = get_memory_service(db)
    n = await svc.delete_all_for_user(user_id=_resolve_user(user_id))
    return {"deleted": n}


# ----- debug / introspection ------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    """Recent sessions with their distillation status."""
    from sqlalchemy import select

    from app.models.memory import Session as ChatSession

    stmt = (
        select(ChatSession)
        .order_by(ChatSession.started_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(s.id),
            "userId": s.user_id,
            "provider": s.provider,
            "startedAt": s.started_at.isoformat(),
            "endedAt": s.ended_at.isoformat() if s.ended_at else None,
            "distilledAt": s.distilled_at.isoformat() if s.distilled_at else None,
        }
        for s in rows
    ]


@router.get("/sessions/{session_id}/turns")
async def list_session_turns(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[dict[str, str]]:
    """Read the short-term Redis buffer for a session (debug)."""
    svc = get_memory_service(db)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = await svc.short_term.list(session_id)
    return [{"role": t.role, "content": t.content, "ts": t.ts} for t in turns]


@router.post("/sessions/{session_id}/distill")
async def distill_session_now(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, int | str]:
    """Re-run distillation for a session synchronously.

    Useful for debugging: ``/end`` schedules distillation in the
    background, but if the LLM returns 0 facts there's no UI signal.
    This endpoint runs it inline and returns the count.
    """
    svc = get_memory_service(db)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Session not found")
    written = await svc.run_distill_now(
        session_id=session_id, user_id=chat.user_id
    )
    return {"sessionId": str(session_id), "written": written}
