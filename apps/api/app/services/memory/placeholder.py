"""Memory placeholder service.

TODO(v0.2): implement short-term conversation memory (redis) and
long-term semantic memory (pgvector).
"""

from __future__ import annotations


class MemoryPlaceholder:
    enabled: bool = False

    def __repr__(self) -> str:
        return "MemoryPlaceholder(enabled=False)"
