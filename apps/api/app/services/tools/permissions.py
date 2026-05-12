"""Tool permission service.

Resolves the effective permission for a (user, tool, scope_key) tuple
against the ``tool_permissions`` table, and writes user decisions
(``allow`` / ``deny``).

Lookup precedence: specific scope, then tool-wide, then policy default.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tools import ToolPermission

PermissionState = Literal["allow", "deny"]


class ToolPermissionService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def resolve(
        self,
        *,
        user_id: str,
        tool_name: str,
        scope_key: str | None,
    ) -> PermissionState | None:
        """Return the most-specific stored decision, or ``None``.

        ``None`` means "no record; fall back to the tool's default_policy".
        """
        if scope_key is not None:
            stmt = select(ToolPermission).where(
                ToolPermission.user_id == user_id,
                ToolPermission.tool_name == tool_name,
                ToolPermission.scope_key == scope_key,
            )
            row = (await self._s.execute(stmt)).scalar_one_or_none()
            if row is not None:
                return row.state  # type: ignore[return-value]

        stmt = select(ToolPermission).where(
            ToolPermission.user_id == user_id,
            ToolPermission.tool_name == tool_name,
            ToolPermission.scope_key.is_(None),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row.state  # type: ignore[return-value]
        return None

    async def set(
        self,
        *,
        user_id: str,
        tool_name: str,
        scope_key: str | None,
        state: PermissionState,
    ) -> ToolPermission:
        # Upsert: find existing exact row, or create.
        stmt = select(ToolPermission).where(
            ToolPermission.user_id == user_id,
            ToolPermission.tool_name == tool_name,
            ToolPermission.scope_key.is_(None)
            if scope_key is None
            else ToolPermission.scope_key == scope_key,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None:
            row = ToolPermission(
                user_id=user_id,
                tool_name=tool_name,
                scope_key=scope_key,
                state=state,
            )
            self._s.add(row)
        else:
            row.state = state
            row.updated_at = now
        await self._s.flush()
        return row

    async def list_for_user(self, user_id: str) -> list[ToolPermission]:
        stmt = (
            select(ToolPermission)
            .where(ToolPermission.user_id == user_id)
            .order_by(ToolPermission.tool_name, ToolPermission.scope_key)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def delete(self, permission_id: uuid.UUID) -> bool:
        row = await self._s.get(ToolPermission, permission_id)
        if row is None:
            return False
        await self._s.delete(row)
        return True

    async def delete_all_for_user(self, user_id: str) -> int:
        result = await self._s.execute(
            delete(ToolPermission).where(ToolPermission.user_id == user_id)
        )
        return int(result.rowcount or 0)

    async def mark_used(
        self,
        *,
        user_id: str,
        tool_name: str,
        scope_key: str | None,
    ) -> None:
        stmt = select(ToolPermission).where(
            ToolPermission.user_id == user_id,
            ToolPermission.tool_name == tool_name,
            ToolPermission.scope_key.is_(None)
            if scope_key is None
            else ToolPermission.scope_key == scope_key,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is not None:
            row.last_used_at = datetime.now(timezone.utc)
