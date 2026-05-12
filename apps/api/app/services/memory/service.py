"""High-level memory façade used by API routes and voice orchestrator.

Owns:
  - session lifecycle (create / end / mark distilled)
  - turn capture into short-term Redis
  - recall (semantic top-K + injection-ready text block)
  - delegation to the background distiller

The façade is intentionally stateless across requests: it composes
stores that wrap connection-scoped objects (AsyncSession, Redis). Use
:func:`get_memory_service` to build one inside a route or task.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.redis import get_redis
from app.models.memory import Fact, Session as ChatSession
from app.services.memory.distiller import distill_session
from app.services.memory.embeddings import embed
from app.services.memory.long_term import LongTermStore
from app.services.memory.short_term import Role, ShortTermStore

log = logging.getLogger("libra.memory")


class MemoryService:
    def __init__(self, *, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.short_term = ShortTermStore(redis)
        self.long_term = LongTermStore(db)

    # ---- sessions ----------------------------------------------------------

    async def start_session(self, *, user_id: str, provider: str) -> uuid.UUID:
        session = ChatSession(user_id=user_id, provider=provider)
        self.db.add(session)
        await self.db.flush()
        return session.id

    async def end_session(self, session_id: uuid.UUID) -> None:
        session = await self.db.get(ChatSession, session_id)
        if session is None or session.ended_at is not None:
            return
        session.ended_at = datetime.now(timezone.utc)

    async def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        return await self.db.get(ChatSession, session_id)

    # ---- turn capture ------------------------------------------------------

    async def record_turn(
        self, *, session_id: uuid.UUID, role: Role, content: str
    ) -> None:
        await self.short_term.append(session_id, role, content)

    # ---- recall ------------------------------------------------------------

    async def recall(
        self, *, user_id: str, query: str, top_k: int | None = None
    ) -> list[tuple[Fact, float]]:
        if not query.strip():
            return []
        settings = get_settings()
        k = top_k or settings.memory_recall_top_k
        vec = await embed(query)
        hits = await self.long_term.search(
            user_id=user_id, embedding=vec, top_k=k
        )
        await self.long_term.mark_recalled([f.id for f, _ in hits])
        return hits

    async def recall_context_block(
        self, *, user_id: str, query: str
    ) -> str | None:
        """Return a prompt-ready string of recalled facts, or None.

        Result is intended to be appended to a system prompt verbatim.
        """
        hits = await self.recall(user_id=user_id, query=query)
        if not hits:
            return None
        lines = [f"- {f.content}" for f, _ in hits]
        return (
            "Relevant things you remember about the user from prior conversations:\n"
            + "\n".join(lines)
        )

    # ---- manual fact CRUD --------------------------------------------------

    async def add_fact(
        self,
        *,
        user_id: str,
        content: str,
        importance: int = 3,
        source_session_id: uuid.UUID | None = None,
    ) -> Fact:
        vec = await embed(content)
        return await self.long_term.add(
            user_id=user_id,
            content=content,
            embedding=vec,
            importance=importance,
            source_session_id=source_session_id,
        )

    async def list_facts(
        self, *, user_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[Fact], int]:
        facts = await self.long_term.list(
            user_id=user_id, limit=limit, offset=offset
        )
        total = await self.long_term.count(user_id=user_id)
        return facts, total

    async def search_facts(
        self, *, user_id: str, query: str, top_k: int = 10
    ) -> list[tuple[Fact, float]]:
        vec = await embed(query)
        return await self.long_term.search(
            user_id=user_id, embedding=vec, top_k=top_k
        )

    async def delete_fact(self, fact_id: uuid.UUID) -> bool:
        return await self.long_term.delete(fact_id)

    async def delete_all_for_user(self, user_id: str) -> int:
        return await self.long_term.delete_all_for_user(user_id=user_id)

    # ---- distillation hook -------------------------------------------------

    async def schedule_distill(
        self, *, session_id: uuid.UUID, user_id: str
    ) -> None:
        """Fire-and-forget background distillation.

        Uses its own DB session because the caller's session may not
        outlive the request that triggered the end. Short-term Redis
        keys are NOT cleared here -- their 1h TTL handles cleanup, and
        leaving them in place lets ``run_distill_now`` re-run against
        the same session for debugging.
        """

        async def _run() -> None:
            try:
                async with session_scope() as db:
                    long_term = LongTermStore(db)
                    written = await distill_session(
                        session_id=session_id,
                        user_id=user_id,
                        short_term=ShortTermStore(get_redis()),
                        long_term=long_term,
                    )
                    # Mark distilled_at unconditionally so the UI / API
                    # can tell distillation has been attempted, even if
                    # it produced 0 facts.
                    result = await db.execute(
                        select(ChatSession).where(ChatSession.id == session_id)
                    )
                    chat = result.scalar_one_or_none()
                    if chat is not None:
                        chat.distilled_at = datetime.now(timezone.utc)
                    log.warning(
                        "distill complete: session=%s wrote=%d", session_id, written
                    )
            except Exception:
                log.exception("distill task failed for session %s", session_id)

        asyncio.create_task(_run())

    async def run_distill_now(
        self, *, session_id: uuid.UUID, user_id: str
    ) -> int:
        """Synchronously run distillation against an existing session.

        Returns the number of facts written. Useful for manual replay /
        debugging via an API endpoint.
        """
        written = await distill_session(
            session_id=session_id,
            user_id=user_id,
            short_term=self.short_term,
            long_term=self.long_term,
        )
        chat = await self.db.get(ChatSession, session_id)
        if chat is not None:
            chat.distilled_at = datetime.now(timezone.utc)
        log.warning(
            "manual distill complete: session=%s wrote=%d", session_id, written
        )
        return written


def get_memory_service(db: AsyncSession) -> MemoryService:
    """Build a MemoryService inside a request handler."""
    return MemoryService(db=db, redis=get_redis())
