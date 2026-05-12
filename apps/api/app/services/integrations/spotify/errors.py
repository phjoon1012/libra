"""Typed errors for the Spotify integration."""

from __future__ import annotations


class SpotifyAuthError(RuntimeError):
    """OAuth flow failed (bad code, refresh rejected, etc.)."""


class SpotifyApiError(RuntimeError):
    """Web API call returned non-2xx with no special handling."""


class SpotifyNotConnected(RuntimeError):
    """A tool tried to act before the user linked an account."""


class SpotifyNotConfigured(RuntimeError):
    """SPOTIFY_CLIENT_ID / _SECRET aren't set in the environment."""


class SpotifyNoActiveDevice(RuntimeError):
    """Spotify accepted the request but the user has no active player."""
