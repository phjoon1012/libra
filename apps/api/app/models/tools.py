"""Tool permission ORM models.

A ``ToolPermission`` row pins a user's grant or denial for a given tool,
optionally narrowed by ``scope_key`` (e.g. a domain for ``fetch_url``).

Lookup precedence at execution time:

1. (user_id, tool_name, scope_key)   -- most specific
2. (user_id, tool_name, NULL)        -- tool-wide
3. tool's ``default_policy``         -- code-level default
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ToolPermission(Base, TimestampMixin):
    __tablename__ = "tool_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "tool_name",
            "scope_key",
            name="uq_tool_permissions_user_tool_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # NULL = applies to the whole tool. Non-NULL narrows by some key the tool
    # defines (e.g. domain for fetch_url, "spotify" for spotify_*).
    scope_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "allow" or "deny"
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
