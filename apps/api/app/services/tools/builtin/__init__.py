"""Built-in tools.

Importing this module side-effect-registers every shipped tool into the
process-wide ``ToolRegistry``. Keep it idempotent.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.tools.builtin.current_time import CurrentTimeTool
from app.services.tools.builtin.spotify import (
    SpotifyNowPlayingTool,
    SpotifyPauseTool,
    SpotifyPlayTool,
    SpotifyResumeTool,
    SpotifySearchTool,
    SpotifySkipTool,
)
from app.services.tools.builtin.weather import WeatherTool
from app.services.tools.registry import get_registry

_REGISTERED = False


def register_builtin_tools() -> None:
    """Idempotent tool registration.

    Spotify tools are only registered when the integration is configured.
    This keeps unconfigured installs from advertising tools the model
    would try to use only to hit ``not_configured`` every time.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    reg = get_registry()
    reg.register(CurrentTimeTool())
    reg.register(WeatherTool())

    settings = get_settings()
    if settings.spotify_client_id and settings.spotify_client_secret:
        reg.register(SpotifySearchTool())
        reg.register(SpotifyPlayTool())
        reg.register(SpotifyPauseTool())
        reg.register(SpotifyResumeTool())
        reg.register(SpotifySkipTool())
        reg.register(SpotifyNowPlayingTool())

    _REGISTERED = True


__all__ = ["register_builtin_tools"]
