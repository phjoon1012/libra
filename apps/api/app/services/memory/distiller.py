"""Conversation distiller.

Reads the raw turns of a finished session out of Redis short-term
storage and asks an LLM to extract a small list of durable, useful
facts. Each fact is embedded and stored in pgvector.

Runs as a background task on session end -- never on the voice path.
"""

from __future__ import annotations

import json
import logging
import uuid

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.memory.embeddings import embed_batch
from app.services.memory.long_term import LongTermStore
from app.services.memory.short_term import ShortTermStore, Turn

log = logging.getLogger("libra.memory.distiller")

DISTILL_SYSTEM_PROMPT = """You read a short voice conversation between a user and their AI assistant (LIBRA) and extract a small list of durable, useful facts about the user, their preferences, ongoing projects, people in their life, or commitments they have made.

Strict rules:
- Only include facts that will plausibly still be true and useful in a future conversation.
- Ignore small talk, jokes, weather, and one-off questions.
- Phrase each fact in third person about the user, starting with "User ".
- Be specific. "User likes coffee" is weak. "User drinks oat-milk lattes in the morning" is good.
- 0 to 6 facts. Empty list is a perfectly valid answer.
- Output ONLY a JSON object: {"facts": [{"content": "...", "importance": 1-5}, ...]}
""".strip()


def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _format_turns(turns: list[Turn]) -> str:
    lines = []
    for t in turns:
        if t.role in ("user", "assistant"):
            speaker = "User" if t.role == "user" else "Assistant"
            lines.append(f"{speaker}: {t.content}")
    return "\n".join(lines)


async def _ask_llm_for_facts(transcript: str) -> list[dict]:
    settings = get_settings()
    if not transcript.strip():
        return []
    completion = await _client().chat.completions.create(
        model=settings.memory_distill_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": DISTILL_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("distiller returned non-JSON: %r", raw[:200])
        return []
    facts = data.get("facts") or []
    if not isinstance(facts, list):
        return []
    cleaned: list[dict] = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        content = (f.get("content") or "").strip()
        if not content:
            continue
        try:
            importance = max(1, min(5, int(f.get("importance", 3))))
        except (TypeError, ValueError):
            importance = 3
        cleaned.append({"content": content, "importance": importance})
    return cleaned


async def distill_session(
    *,
    session_id: uuid.UUID,
    user_id: str,
    short_term: ShortTermStore,
    long_term: LongTermStore,
) -> int:
    """Extract + persist facts from a session. Returns count written.

    Caller is responsible for committing the SQLAlchemy session.
    """
    turns = await short_term.list(session_id)
    if not turns:
        log.warning(
            "distiller: short-term buffer empty for session %s; skipping",
            session_id,
        )
        return 0
    transcript = _format_turns(turns)
    log.warning(
        "distiller: session=%s turns=%d transcript_chars=%d",
        session_id,
        len(turns),
        len(transcript),
    )
    facts = await _ask_llm_for_facts(transcript)
    if not facts:
        log.warning(
            "distiller: LLM returned 0 facts for session %s (transcript head: %r)",
            session_id,
            transcript[:300],
        )
        return 0
    embeddings = await embed_batch([f["content"] for f in facts])
    for f, vec in zip(facts, embeddings):
        await long_term.add(
            user_id=user_id,
            content=f["content"],
            embedding=vec,
            importance=f["importance"],
            source_session_id=session_id,
        )
    log.warning(
        "distiller: wrote %d facts for session %s: %s",
        len(facts),
        session_id,
        [f["content"] for f in facts],
    )
    return len(facts)
