"""Tools placeholder service.

TODO(v0.3+): implement a tool registry. Every tool that performs a
real-world action must declare its required permission level. Execution
goes through an explicit permission layer; no silent side effects.
"""

from __future__ import annotations


class ToolRegistryPlaceholder:
    enabled: bool = False

    def list(self) -> list[str]:
        return []
