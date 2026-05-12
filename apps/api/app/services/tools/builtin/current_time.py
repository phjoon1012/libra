"""current_time tool.

Returns the current time, optionally in a requested IANA timezone.
Autorun: no side effects, no PII, no quota.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.tools.base import ExecutionContext, Tool, ToolResult


class CurrentTimeTool(Tool):
    name = "current_time"
    description = (
        "Return the current date and time. "
        "Pass an IANA timezone name (e.g. 'America/Los_Angeles') to "
        "localise the result; otherwise UTC is used."
    )
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name. Optional; defaults to UTC.",
            }
        },
        "additionalProperties": False,
    }
    default_policy = "autorun"

    async def run(
        self, args: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        tz_name = (args or {}).get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            return ToolResult(
                content=f"Unknown timezone {tz_name!r}.", error=True
            )
        now = datetime.now(tz)
        return ToolResult(
            content=now.strftime("%A, %B %-d %Y at %-I:%M %p %Z"),
            data={
                "iso": now.isoformat(),
                "timezone": tz_name,
                "epoch": int(now.timestamp()),
            },
        )
