"""Wire schemas for the tools API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    default_policy: Literal["autorun", "ask", "denied"]


class ToolListResponse(BaseModel):
    tools: list[ToolDescriptor]


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., alias="toolName")
    args: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = Field(default=None, alias="userId")
    session_id: uuid.UUID | None = Field(default=None, alias="sessionId")
    # If True, run this call without consulting/storing permission decision.
    approve_once: bool = Field(default=False, alias="approveOnce")

    class Config:
        populate_by_name = True


class ToolExecuteResponse(BaseModel):
    status: Literal["ok", "pending", "denied", "error"]
    request_id: str | None = Field(default=None, alias="requestId")
    tool_name: str = Field(..., alias="toolName")
    # The LLM-shaped payload (JSON-encoded dict). Front-end may parse.
    content: str | None = None
    data: Any = None
    error: bool = False
    reason: str | None = None
    scope_key: str | None = Field(default=None, alias="scopeKey")

    class Config:
        populate_by_name = True


class ToolPermissionOut(BaseModel):
    id: uuid.UUID
    user_id: str = Field(..., alias="userId")
    tool_name: str = Field(..., alias="toolName")
    scope_key: str | None = Field(default=None, alias="scopeKey")
    state: Literal["allow", "deny"]
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    last_used_at: datetime | None = Field(default=None, alias="lastUsedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class ToolPermissionUpsert(BaseModel):
    tool_name: str = Field(..., alias="toolName")
    state: Literal["allow", "deny"]
    scope_key: str | None = Field(default=None, alias="scopeKey")
    user_id: str | None = Field(default=None, alias="userId")

    class Config:
        populate_by_name = True
