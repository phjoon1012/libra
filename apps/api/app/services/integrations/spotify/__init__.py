"""Spotify integration package.

Public surface:

- ``SpotifyService`` — high-level helper that owns OAuth + API calls,
  handles token refresh transparently.
- ``SpotifyAuthError`` / ``SpotifyApiError`` — typed errors that route
  handlers and tools convert into user-facing messages.
"""

from __future__ import annotations

from app.services.integrations.spotify.errors import (
    SpotifyApiError,
    SpotifyAuthError,
    SpotifyNotConnected,
    SpotifyNotConfigured,
    SpotifyNoActiveDevice,
)
from app.services.integrations.spotify.service import SpotifyService

__all__ = [
    "SpotifyApiError",
    "SpotifyAuthError",
    "SpotifyNotConnected",
    "SpotifyNotConfigured",
    "SpotifyNoActiveDevice",
    "SpotifyService",
]
