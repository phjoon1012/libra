"""Tool executor.

Single chokepoint for every tool invocation. Resolves permissions,
runs the tool, marks usage. Returns one of ``ToolResult``,
``ToolPending``, or ``ToolDenied``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tools.base import (
    ExecutionContext,
    ToolDenied,
    ToolOutcome,
    ToolPending,
    ToolResult,
)
from app.services.tools.permissions import ToolPermissionService
from app.services.tools.registry import get_registry

log = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._perms = ToolPermissionService(db)

    async def execute(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        ctx: ExecutionContext,
        approval_override: bool | None = None,
    ) -> ToolOutcome:
        """Run a tool.

        ``approval_override``:
        - ``None`` (default): consult stored permission + default policy
        - ``True``: caller has user consent for this one call (don't store)
        - ``False``: caller asked to refuse despite policy
        """
        tool = get_registry().get(tool_name)
        if tool is None:
            return ToolDenied(tool_name=tool_name, reason="unknown tool")

        scope_key = tool.scope_key_for(args)
        stored = await self._perms.resolve(
            user_id=ctx.user_id, tool_name=tool_name, scope_key=scope_key
        )

        if approval_override is False:
            return ToolDenied(tool_name=tool_name, reason="denied by user")

        effective: str | None
        if approval_override is True:
            effective = "allow"
        elif stored is not None:
            effective = stored
        else:
            # No stored decision -- fall back to tool's policy.
            if tool.default_policy == "autorun":
                effective = "allow"
            elif tool.default_policy == "denied":
                effective = "deny"
            else:  # "ask"
                return ToolPending(
                    tool_name=tool_name,
                    args=args,
                    scope_key=scope_key,
                    request_id=ctx.request_id,
                )

        if effective == "deny":
            return ToolDenied(tool_name=tool_name, reason="denied by policy")

        try:
            result = await tool.run(args, ctx)
        except Exception as exc:  # noqa: BLE001
            log.exception("Tool %s raised", tool_name)
            return ToolResult(
                content=f"Tool {tool_name} failed: {exc!s}",
                error=True,
            )

        await self._perms.mark_used(
            user_id=ctx.user_id, tool_name=tool_name, scope_key=scope_key
        )
        return result
