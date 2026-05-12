"""Spotify tools.

All six share the same shape: open a SpotifyService for the user, run
the call, translate typed errors into ToolResult(error=True). Consent
is granted by *connecting* the account in Settings — once connected,
spotify_* tools autorun (scope_key="spotify").
"""

from __future__ import annotations

from typing import Any

from app.core.db import session_scope
from app.services.integrations.spotify import (
    SpotifyApiError,
    SpotifyAuthError,
    SpotifyNoActiveDevice,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyService,
)
from app.services.tools.base import ExecutionContext, Tool, ToolResult


def _scope_key(_args: dict[str, Any]) -> str | None:
    return "spotify"


def _err(msg: str) -> ToolResult:
    return ToolResult(content=msg, error=True)


async def _with_service(user_id: str, fn):  # type: ignore[no-untyped-def]
    """Run an async closure that takes a SpotifyService, opening a DB
    session per call so we don't hold a connection across tool turns."""
    try:
        async with session_scope() as db:
            svc = SpotifyService(db)
            return await fn(svc)
    except SpotifyNotConfigured as exc:
        return _err(
            "Spotify isn't set up on the server (missing SPOTIFY_CLIENT_ID / "
            f"_SECRET): {exc}"
        )
    except SpotifyNotConnected as exc:
        return _err(str(exc))
    except SpotifyNoActiveDevice as exc:
        return _err(str(exc))
    except (SpotifyAuthError, SpotifyApiError) as exc:
        return _err(f"Spotify error: {exc}")


# ----- search ---------------------------------------------------------------


class SpotifySearchTool(Tool):
    name = "spotify_search"
    description = (
        "Search Spotify for tracks, albums, artists, or playlists. "
        "Returns the top matches with Spotify URIs that other Spotify "
        "tools can use."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text search, e.g. 'daft punk one more time'.",
            },
            "type": {
                "type": "string",
                "enum": ["track", "album", "artist", "playlist"],
                "description": "What to search for. Defaults to track.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "How many results to return. Defaults to 5.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        query = (args.get("query") or "").strip()
        if not query:
            return _err("query is required")
        kind = args.get("type") or "track"
        limit = int(args.get("limit") or 5)

        async def call(svc: SpotifyService) -> ToolResult:
            body = await svc.search(
                ctx.user_id, query=query, kind=kind, limit=limit
            )
            bucket = body.get(f"{kind}s", {}).get("items", []) or []
            items: list[dict[str, Any]] = []
            for it in bucket:
                if kind == "track":
                    items.append(
                        {
                            "name": it["name"],
                            "artists": [a["name"] for a in it.get("artists", [])],
                            "album": (it.get("album") or {}).get("name"),
                            "uri": it["uri"],
                        }
                    )
                elif kind == "album":
                    items.append(
                        {
                            "name": it["name"],
                            "artists": [a["name"] for a in it.get("artists", [])],
                            "uri": it["uri"],
                        }
                    )
                elif kind == "artist":
                    items.append({"name": it["name"], "uri": it["uri"]})
                elif kind == "playlist":
                    items.append(
                        {
                            "name": it["name"],
                            "owner": (it.get("owner") or {}).get("display_name"),
                            "uri": it["uri"],
                        }
                    )
            if not items:
                return ToolResult(
                    content=f"No {kind} matches for {query!r}.",
                    data={"items": []},
                )
            head = items[0]
            if kind == "track":
                summary = (
                    f"Top match: {head['name']} by "
                    f"{', '.join(head['artists'])} ({head['album']})."
                )
            else:
                summary = f"Top {kind}: {head['name']}."
            return ToolResult(
                content=summary,
                data={"kind": kind, "items": items},
            )

        return await _with_service(ctx.user_id, call)


# ----- play -----------------------------------------------------------------


class SpotifyPlayTool(Tool):
    name = "spotify_play"
    description = (
        "Play music on the user's active Spotify device. Pass a Spotify "
        "URI (recommended; from spotify_search) or a free-text query to "
        "search-and-play. The user's Spotify must be open somewhere "
        "(desktop, phone, web player). Requires Spotify Premium."
    )
    parameters = {
        "type": "object",
        "properties": {
            "uri": {
                "type": "string",
                "description": (
                    "Spotify URI of a track / album / artist / playlist. "
                    "Track URIs are played directly; album/artist/playlist "
                    "are played as a context. Optional if 'query' is set."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Free-text fallback: searches Spotify for the top "
                    "track and plays it. Ignored if 'uri' is set."
                ),
            },
        },
        "additionalProperties": False,
    }
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        uri = (args.get("uri") or "").strip() or None
        query = (args.get("query") or "").strip() or None
        if not uri and not query:
            return _err("Provide either 'uri' or 'query'.")

        async def call(svc: SpotifyService) -> ToolResult:
            nonlocal uri
            label = uri or query
            if not uri and query:
                body = await svc.search(ctx.user_id, query=query, kind="track", limit=1)
                items = body.get("tracks", {}).get("items", []) or []
                if not items:
                    return _err(f"No tracks found for {query!r}.")
                top = items[0]
                uri = top["uri"]
                label = (
                    f"{top['name']} by "
                    f"{', '.join(a['name'] for a in top.get('artists', []))}"
                )

            uris: list[str] | None = None
            context_uri: str | None = None
            if uri.startswith("spotify:track:"):
                uris = [uri]
            else:
                # album / artist / playlist all play as contexts.
                context_uri = uri

            await svc.play(ctx.user_id, uris=uris, context_uri=context_uri)
            return ToolResult(
                content=f"Playing {label}.",
                data={"uri": uri},
            )

        return await _with_service(ctx.user_id, call)


# ----- pause / resume / skip / now_playing ----------------------------------


class SpotifyPauseTool(Tool):
    name = "spotify_pause"
    description = "Pause Spotify playback on the active device."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        async def call(svc: SpotifyService) -> ToolResult:
            await svc.pause(ctx.user_id)
            return ToolResult(content="Paused.")

        return await _with_service(ctx.user_id, call)


class SpotifyResumeTool(Tool):
    name = "spotify_resume"
    description = "Resume Spotify playback on the active device."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        async def call(svc: SpotifyService) -> ToolResult:
            await svc.resume(ctx.user_id)
            return ToolResult(content="Resumed.")

        return await _with_service(ctx.user_id, call)


class SpotifySkipTool(Tool):
    name = "spotify_skip"
    description = "Skip to the next or previous track on Spotify."
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["next", "previous"],
                "description": "Defaults to 'next'.",
            }
        },
        "additionalProperties": False,
    }
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        direction = args.get("direction") or "next"
        if direction not in ("next", "previous"):
            return _err("direction must be 'next' or 'previous'")

        async def call(svc: SpotifyService) -> ToolResult:
            await svc.skip(ctx.user_id, direction=direction)
            return ToolResult(content=f"Skipped to {direction} track.")

        return await _with_service(ctx.user_id, call)


class SpotifyNowPlayingTool(Tool):
    name = "spotify_now_playing"
    description = "Return what's currently playing on the user's Spotify."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    default_policy = "autorun"

    def scope_key_for(self, args: dict[str, Any]) -> str | None:
        return _scope_key(args)

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        async def call(svc: SpotifyService) -> ToolResult:
            body = await svc.now_playing(ctx.user_id)
            if body is None:
                return ToolResult(content="Nothing is currently playing.")
            item = body.get("item") or {}
            if not item:
                return ToolResult(content="Nothing is currently playing.")
            name = item.get("name") or "Unknown"
            artists = ", ".join(
                a["name"] for a in (item.get("artists") or [])
            )
            album = (item.get("album") or {}).get("name") or ""
            is_playing = body.get("is_playing", True)
            verb = "Playing" if is_playing else "Paused"
            summary = f"{verb}: {name} by {artists} ({album})."
            return ToolResult(
                content=summary,
                data={
                    "isPlaying": is_playing,
                    "track": name,
                    "artists": [a["name"] for a in (item.get("artists") or [])],
                    "album": album,
                    "uri": item.get("uri"),
                },
            )

        return await _with_service(ctx.user_id, call)
