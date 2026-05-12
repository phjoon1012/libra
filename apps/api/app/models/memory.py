"""Memory-related ORM models.

Schema overview
---------------

``sessions``
    One row per voice conversation. Created when the browser POSTs
    ``/api/voice/session`` and closed when the client signals end (or
    the backend infers it from a WS close). End-of-session triggers
    the distiller as a background task.

``facts``
    Durable, distilled facts extracted from conversation turns. Each
    row carries a 1536-dim ``vector`` embedding (matches OpenAI
    ``text-embedding-3-small``). Indexed with an HNSW index for fast
    cosine-similarity search.

Raw per-turn transcripts are intentionally NOT persisted by default;
they live only in Redis short-term memory. This keeps the long-term
store small, useful, and easy to audit/delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, _utcnow

EMBEDDING_DIM = 1536


if TYPE_CHECKING:
    pass


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    distilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    facts: Mapped[list["Fact"]] = relationship(back_populates="source_session")


class Fact(Base, TimestampMixin):
    __tablename__ = "facts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 1 (trivia) .. 5 (highly important). Used as a recall tie-breaker.
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=False
    )
    last_recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source_session: Mapped[Session | None] = relationship(back_populates="facts")


# HNSW index for cosine similarity. Created in migration; declared here
# so SQLAlchemy knows about it for metadata operations.
Index(
    "ix_facts_embedding_hnsw",
    Fact.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
