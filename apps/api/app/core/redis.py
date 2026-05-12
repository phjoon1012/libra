"""Async Redis client.

Shared single instance per process. Used for short-term memory (rolling
session turn buffer) and any future event-bus needs.
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis, from_url

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not configured")
    return from_url(
        settings.redis_url,
        decode_responses=True,
        health_check_interval=30,
    )
