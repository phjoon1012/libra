"""Tool API.

- ``GET  /api/tools``                  list registered tools
- ``POST /api/tools/execute``          run a tool (with permission check)
- ``GET  /api/tools/permissions``      list stored permissions for a user
- ``POST /api/tools/permissions``      upsert a permission decision
- ``DELETE /api/tools/permissions/{id}``  remove a permission decision
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.schemas.tools import (
    ToolDescriptor,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolListResponse,
    ToolPermissionOut,
    ToolPermissionUpsert,
)
from app.services.tools import (
    ExecutionContext,
    ToolDenied,
    ToolExecutor,
    ToolPending,
    ToolPermissionService,
    ToolResult,
    get_registry,
    register_builtin_tools,
)

router = APIRouter()


def _resolve_user(user_id: str | None) -> str:
    return user_id or get_settings().memory_default_user_id


@router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    # Defensive: in case lifespan didn't run (e.g. during tests).
    register_builtin_tools()
    tools = [
        ToolDescriptor(
            name=t.name,
            description=t.description,
            parameters=t.parameters,
            default_policy=t.default_policy,
        )
        for t in get_registry().list()
    ]
    return ToolListResponse(tools=tools)


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    payload: ToolExecuteRequest, db: AsyncSession = Depends(get_db)
) -> ToolExecuteResponse:
    register_builtin_tools()
    ctx = ExecutionContext(
        user_id=_resolve_user(payload.user_id),
        session_id=payload.session_id,
    )
    executor = ToolExecutor(db)
    outcome = await executor.execute(
        tool_name=payload.tool_name,
        args=payload.args,
        ctx=ctx,
        approval_override=True if payload.approve_once else None,
    )

    if isinstance(outcome, ToolResult):
        return ToolExecuteResponse(
            status="error" if outcome.error else "ok",
            tool_name=payload.tool_name,
            request_id=ctx.request_id,
            content=outcome.content,
            data=outcome.data,
            error=outcome.error,
        )
    if isinstance(outcome, ToolPending):
        return ToolExecuteResponse(
            status="pending",
            tool_name=outcome.tool_name,
            request_id=outcome.request_id,
            reason=outcome.reason,
            scope_key=outcome.scope_key,
        )
    if isinstance(outcome, ToolDenied):
        return ToolExecuteResponse(
            status="denied",
            tool_name=outcome.tool_name,
            request_id=ctx.request_id,
            reason=outcome.reason,
        )
    raise HTTPException(status_code=500, detail="unknown tool outcome")


@router.get("/permissions", response_model=list[ToolPermissionOut])
async def list_permissions(
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> list[ToolPermissionOut]:
    svc = ToolPermissionService(db)
    rows = await svc.list_for_user(_resolve_user(user_id))
    return [ToolPermissionOut.model_validate(r) for r in rows]


@router.post(
    "/permissions",
    response_model=ToolPermissionOut,
    status_code=status.HTTP_200_OK,
)
async def upsert_permission(
    payload: ToolPermissionUpsert, db: AsyncSession = Depends(get_db)
) -> ToolPermissionOut:
    svc = ToolPermissionService(db)
    row = await svc.set(
        user_id=_resolve_user(payload.user_id),
        tool_name=payload.tool_name,
        scope_key=payload.scope_key,
        state=payload.state,
    )
    return ToolPermissionOut.model_validate(row)


@router.delete(
    "/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_permission(
    permission_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    svc = ToolPermissionService(db)
    deleted = await svc.delete(permission_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Permission not found")


@router.delete("/permissions", status_code=status.HTTP_200_OK)
async def delete_all_permissions(
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    svc = ToolPermissionService(db)
    n = await svc.delete_all_for_user(_resolve_user(user_id))
    return {"deleted": n}
