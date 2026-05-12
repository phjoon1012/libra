"""Memory subsystem.

Exposes :class:`MemoryService` as the single entry point used by the
voice orchestrator and API routes. Individual stores live in sibling
modules.
"""

from app.services.memory.service import MemoryService, get_memory_service

__all__ = ["MemoryService", "get_memory_service"]
