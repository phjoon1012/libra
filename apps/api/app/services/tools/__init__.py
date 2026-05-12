"""LIBRA tools subsystem.

Public surface:

- ``Tool``, ``ToolResult``, ``ToolPending``, ``ToolDenied``,
  ``ExecutionContext`` -- the abstractions tools implement and emit.
- ``ToolExecutor`` -- single chokepoint for execution + permission checks.
- ``get_registry`` -- access to the registered tool list.
- ``register_builtin_tools`` -- side-effect registers shipped tools.
"""

from __future__ import annotations

from app.services.tools.base import (
    ExecutionContext,
    PermissionPolicy,
    PermissionState,
    Tool,
    ToolDenied,
    ToolOutcome,
    ToolPending,
    ToolResult,
)
from app.services.tools.builtin import register_builtin_tools
from app.services.tools.executor import ToolExecutor
from app.services.tools.permissions import ToolPermissionService
from app.services.tools.registry import ToolRegistry, get_registry

__all__ = [
    "ExecutionContext",
    "PermissionPolicy",
    "PermissionState",
    "Tool",
    "ToolDenied",
    "ToolExecutor",
    "ToolOutcome",
    "ToolPending",
    "ToolPermissionService",
    "ToolRegistry",
    "ToolResult",
    "get_registry",
    "register_builtin_tools",
]
