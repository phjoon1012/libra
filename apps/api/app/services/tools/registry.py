"""Tool registry singleton.

Process-wide, populated at import time. Tools register themselves by
being instantiated in ``app.services.tools.builtin``.
"""

from __future__ import annotations

from app.services.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise RuntimeError(f"Tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry
