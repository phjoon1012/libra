"""Long-term memory: Postgres + pgvector.

Stores distilled :class:`Fact` rows with cosine-similarity vector
search. Search returns (fact, score) tuples where ``score`` is the
cosine distance in [0, 2]; lower = more similar.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact


class LongTermStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        *,
        user_id: str,
        content: str,
        embedding: list[float],
        importance: int = 3,
        source_session_id: uuid.UUID | None = None,
    ) -> Fact:
        fact = Fact(
            user_id=user_id,
            content=content,
            embedding=embedding,
            importance=importance,
            source_session_id=source_session_id,
        )
        self._s.add(fact)
        await self._s.flush()
        return fact

    async def search(
        self,
        *,
        user_id: str,
        embedding: list[float],
        top_k: int = 5,
    ) -> list[tuple[Fact, float]]:
        distance = Fact.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(Fact, distance)
            .where(Fact.user_id == user_id)
            .order_by(distance.asc(), Fact.importance.desc())
            .limit(top_k)
        )
        result = await self._s.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def list(
        self,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Fact]:
        stmt = (
            select(Fact)
            .where(Fact.user_id == user_id)
            .order_by(Fact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, user_id: str) -> int:
        stmt = select(func.count()).select_from(Fact).where(Fact.user_id == user_id)
        return int((await self._s.execute(stmt)).scalar_one())

    async def get(self, fact_id: uuid.UUID) -> Fact | None:
        return await self._s.get(Fact, fact_id)

    async def delete(self, fact_id: uuid.UUID) -> bool:
        fact = await self._s.get(Fact, fact_id)
        if fact is None:
            return False
        await self._s.delete(fact)
        return True

    async def delete_all_for_user(self, user_id: str) -> int:
        result = await self._s.execute(
            delete(Fact).where(Fact.user_id == user_id)
        )
        return int(result.rowcount or 0)

    async def mark_recalled(self, fact_ids: list[uuid.UUID]) -> None:
        if not fact_ids:
            return
        now = datetime.now(timezone.utc)
        for fid in fact_ids:
            fact = await self._s.get(Fact, fid)
            if fact is not None:
                fact.last_recalled_at = now
