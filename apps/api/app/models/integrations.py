"""Third-party integration tokens.

For v0.3 we store Spotify OAuth tokens in plaintext: this is a
single-user local deployment and the DB is private to the host. When
multi-user lands, encrypt at rest with a per-row key. Marked TODO.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SpotifyAccount(Base, TimestampMixin):
    """One Spotify account linked to a LIBRA user."""

    __tablename__ = "spotify_accounts"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    spotify_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # TODO(multi-user): encrypt at rest with a per-row key.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Internal stable id (in case the row gets rotated).
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid.uuid4, nullable=False, unique=True
    )
