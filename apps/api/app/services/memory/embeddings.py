"""OpenAI embedding wrapper.

Single async function used by both the long-term store (when writing
facts) and the recall path (when embedding the recall query).
"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import get_settings


def _client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def embed(text: str) -> list[float]:
    settings = get_settings()
    resp = await _client().embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )
    return list(resp.data[0].embedding)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    resp = await _client().embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [list(d.embedding) for d in resp.data]
