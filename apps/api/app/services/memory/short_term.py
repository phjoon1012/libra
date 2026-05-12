"""Short-term memory: Redis-backed rolling buffer of conversation turns.

Each session has a Redis list keyed by ``libra:session:{session_id}:turns``
containing JSON-encoded ``{role, content, ts}`` entries. The list is
trimmed to the last ``memory_short_term_max_turns`` entries on every
append. Sessions expire 1 hour after the last write so dormant
sessions don't leak memory; the distiller copies anything important
into long-term storage before that happens.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from redis.asyncio import Redis

from app.core.config import get_settings

Role = Literal["user", "assistant", "system"]
SESSION_TTL_SECONDS = 60 * 60  # 1 hour


@dataclass(slots=True)
class Turn:
    role: Role
    content: str
    ts: str  # ISO-8601 UTC

    def to_json(self) -> str:
        return json.dumps({"role": self.role, "content": self.content, "ts": self.ts})

    @classmethod
    def from_json(cls, raw: str) -> "Turn":
        d = json.loads(raw)
        return cls(role=d["role"], content=d["content"], ts=d["ts"])


def _key(session_id: uuid.UUID | str) -> str:
    return f"libra:session:{session_id}:turns"


class ShortTermStore:
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def append(
        self, session_id: uuid.UUID | str, role: Role, content: str
    ) -> None:
        if not content.strip():
            return
        turn = Turn(
            role=role,
            content=content,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        key = _key(session_id)
        settings = get_settings()
        pipe = self._r.pipeline()
        pipe.rpush(key, turn.to_json())
        pipe.ltrim(key, -settings.memory_short_term_max_turns, -1)
        pipe.expire(key, SESSION_TTL_SECONDS)
        await pipe.execute()

    async def list(self, session_id: uuid.UUID | str) -> list[Turn]:
        raw = await self._r.lrange(_key(session_id), 0, -1)
        return [Turn.from_json(x) for x in raw]

    async def recent_user_text(
        self, session_id: uuid.UUID | str, n: int = 3
    ) -> str:
        """Last ``n`` user utterances joined with newlines.

        Used as the recall query basis: we want the model to remember
        things tied to what the user is currently talking about.
        """
        turns = await self.list(session_id)
        user_turns = [t.content for t in turns if t.role == "user"][-n:]
        return "\n".join(user_turns)

    async def clear(self, session_id: uuid.UUID | str) -> None:
        await self._r.delete(_key(session_id))
