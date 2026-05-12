"""Tool framework: base types.

A tool is a structured capability the LLM can invoke. Every tool:

- declares a JSON Schema for its arguments (OpenAI tool format),
- declares a ``default_policy`` (autorun / ask / denied),
- optionally derives a ``scope_key`` from its args so permissions can
  be narrowed (e.g. fetch_url -> domain, spotify_* -> "spotify"),
- implements ``run`` returning a JSON-serialisable result.

Execution always goes through ``ToolExecutor``, never the tool directly.
"""

from __future__ import annotations

import abc
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

PermissionPolicy = Literal["autorun", "ask", "denied"]
PermissionState = Literal["allow", "deny"]


@dataclass(slots=True)
class ExecutionContext:
    """Runtime context handed to every tool invocation."""

    user_id: str
    session_id: uuid.UUID | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass(slots=True)
class ToolResult:
    """Successful execution result.

    ``content`` is a short human/LLM-readable summary. ``data`` is the
    structured payload returned to the model (will be JSON-encoded).
    """

    content: str
    data: dict[str, Any] | list[Any] | None = None
    error: bool = False

    def to_llm_payload(self) -> str:
        body: dict[str, Any] = {"content": self.content}
        if self.data is not None:
            body["data"] = self.data
        if self.error:
            body["error"] = True
        return json.dumps(body, ensure_ascii=False)


@dataclass(slots=True)
class ToolPending:
    """Returned when the user must approve before execution proceeds."""

    tool_name: str
    args: dict[str, Any]
    scope_key: str | None
    request_id: str
    reason: str = "approval_required"


@dataclass(slots=True)
class ToolDenied:
    """Returned when policy or explicit denial blocks the call."""

    tool_name: str
    reason: str

    def to_llm_payload(self) -> str:
        return json.dumps(
            {
                "error": True,
                "denied": True,
                "reason": self.reason,
            }
        )


ToolOutcome = ToolResult | ToolPending | ToolDenied


class Tool(abc.ABC):
    """Abstract base. Subclasses are stateless and reusable."""

    #: Stable identifier used by the LLM and stored in the permissions table.
    name: str
    #: One-line description shown to the LLM.
    description: str
    #: JSON Schema for arguments (OpenAI tool ``parameters`` format).
    parameters: dict[str, Any]
    #: Default policy when no user grant exists.
    default_policy: PermissionPolicy = "ask"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:  # noqa: ARG002
        """Optionally narrow permissions by some property of the args.

        Default: tool-wide grant (no scoping).
        """
        return None

    @abc.abstractmethod
    async def run(
        self, args: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult: ...

    def to_openai_tool(self) -> dict[str, Any]:
        """Render this tool in the OpenAI ``tools[]`` request format."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def measure(start: float) -> float:
    """Helper for tools that want to report duration."""
    return round((time.monotonic() - start) * 1000)
