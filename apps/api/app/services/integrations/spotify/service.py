"""Spotify service: OAuth, token refresh, and Web API calls.

Designed to be instantiated per-request with an ``AsyncSession``. Owns
the round trip to Spotify and persists token refreshes back into the
``spotify_accounts`` row.

Scopes requested:
    user-read-private          basic account info (display name, product)
    user-read-email            account identity
    user-read-playback-state   read current playback + device list
    user-modify-playback-state play / pause / skip / volume
    user-read-currently-playing
"""

from __future__ import annotations

import base64
import logging
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.integrations import SpotifyAccount
from app.services.integrations.spotify.errors import (
    SpotifyApiError,
    SpotifyAuthError,
    SpotifyNoActiveDevice,
    SpotifyNotConfigured,
    SpotifyNotConnected,
)

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
HTTP_TIMEOUT = 8.0

SCOPES = " ".join(
    [
        "user-read-private",
        "user-read-email",
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
    ]
)


class SpotifyService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self._db = db
        self._s = settings or get_settings()

    # ----- configuration / discovery ---------------------------------------

    @property
    def is_configured(self) -> bool:
        return bool(self._s.spotify_client_id and self._s.spotify_client_secret)

    def _require_config(self) -> None:
        if not self.is_configured:
            raise SpotifyNotConfigured(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are not set."
            )

    # ----- OAuth -----------------------------------------------------------

    def build_authorize_url(self, *, state: str | None = None) -> tuple[str, str]:
        """Return ``(authorize_url, state)``. Caller should store state."""
        self._require_config()
        chosen_state = state or secrets.token_urlsafe(24)
        params = {
            "client_id": self._s.spotify_client_id,
            "response_type": "code",
            "redirect_uri": self._s.spotify_redirect_uri,
            "scope": SCOPES,
            "state": chosen_state,
            "show_dialog": "true",
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}", chosen_state

    async def exchange_code(self, code: str) -> dict[str, Any]:
        self._require_config()
        auth = base64.b64encode(
            f"{self._s.spotify_client_id}:{self._s.spotify_client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._s.spotify_redirect_uri,
                },
            )
        if resp.status_code != 200:
            raise SpotifyAuthError(
                f"token exchange failed: HTTP {resp.status_code} {resp.text}"
            )
        return resp.json()

    async def _refresh_tokens(self, account: SpotifyAccount) -> None:
        self._require_config()
        auth = base64.b64encode(
            f"{self._s.spotify_client_id}:{self._s.spotify_client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": account.refresh_token,
                },
            )
        if resp.status_code != 200:
            raise SpotifyAuthError(
                f"refresh failed: HTTP {resp.status_code} {resp.text}"
            )
        payload = resp.json()
        account.access_token = payload["access_token"]
        if "refresh_token" in payload:
            account.refresh_token = payload["refresh_token"]
        expires_in = int(payload.get("expires_in", 3600))
        account.expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in - 60  # refresh a touch early
        )
        await self._db.flush()

    async def link_account(self, *, user_id: str, code: str) -> SpotifyAccount:
        """Run the code exchange + write/update the account row.

        After this call returns, the account is ready for API use.
        """
        payload = await self.exchange_code(code)
        access_token: str = payload["access_token"]
        refresh_token: str = payload["refresh_token"]
        expires_in = int(payload.get("expires_in", 3600))
        scope: str = payload.get("scope", SCOPES)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            me = await client.get(
                f"{API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if me.status_code != 200:
            raise SpotifyAuthError(
                f"/me probe failed: HTTP {me.status_code} {me.text}"
            )
        me_body = me.json()

        account = await self._db.get(SpotifyAccount, user_id)
        if account is None:
            account = SpotifyAccount(
                user_id=user_id,
                spotify_user_id=me_body["id"],
                display_name=me_body.get("display_name"),
                product=me_body.get("product"),
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope,
                connected_at=datetime.now(timezone.utc),
            )
            self._db.add(account)
        else:
            account.spotify_user_id = me_body["id"]
            account.display_name = me_body.get("display_name")
            account.product = me_body.get("product")
            account.access_token = access_token
            account.refresh_token = refresh_token
            account.expires_at = expires_at
            account.scope = scope
            account.connected_at = datetime.now(timezone.utc)
        await self._db.flush()
        return account

    async def get_account(self, user_id: str) -> SpotifyAccount | None:
        return (
            await self._db.execute(
                select(SpotifyAccount).where(SpotifyAccount.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def disconnect(self, user_id: str) -> bool:
        account = await self.get_account(user_id)
        if account is None:
            return False
        await self._db.delete(account)
        return True

    # ----- authenticated API calls -----------------------------------------

    async def _authed_account(self, user_id: str) -> SpotifyAccount:
        account = await self.get_account(user_id)
        if account is None:
            raise SpotifyNotConnected(
                "No Spotify account is connected. Connect one in Settings."
            )
        # Refresh if expiring within the next 30s.
        if account.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=30):
            await self._refresh_tokens(account)
        return account

    async def _request(
        self,
        user_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        account = await self._authed_account(user_id)
        headers = {"Authorization": f"Bearer {account.access_token}"}

        async def call(token: str) -> httpx.Response:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                return await client.request(
                    method,
                    f"{API_BASE}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    json=json,
                )

        resp = await call(account.access_token)
        if resp.status_code == 401:
            # Token was invalidated server-side. Force a refresh and retry once.
            await self._refresh_tokens(account)
            resp = await call(account.access_token)
        return resp

    # ----- public Web API helpers ------------------------------------------

    async def search(
        self,
        user_id: str,
        *,
        query: str,
        kind: str = "track",
        limit: int = 5,
    ) -> dict[str, Any]:
        resp = await self._request(
            user_id,
            "GET",
            "/search",
            params={"q": query, "type": kind, "limit": limit},
        )
        if resp.status_code != 200:
            raise SpotifyApiError(f"search failed: {resp.status_code} {resp.text}")
        return resp.json()

    async def list_devices(self, user_id: str) -> list[dict[str, Any]]:
        resp = await self._request(user_id, "GET", "/me/player/devices")
        if resp.status_code != 200:
            raise SpotifyApiError(
                f"devices failed: {resp.status_code} {resp.text}"
            )
        return resp.json().get("devices", [])

    async def pick_active_device(self, user_id: str) -> str | None:
        devices = await self.list_devices(user_id)
        if not devices:
            return None
        # Prefer "is_active" then "is_restricted=false" then anything.
        for d in devices:
            if d.get("is_active") and not d.get("is_restricted"):
                return d["id"]
        for d in devices:
            if not d.get("is_restricted"):
                return d["id"]
        return devices[0]["id"]

    async def now_playing(self, user_id: str) -> dict[str, Any] | None:
        resp = await self._request(
            user_id, "GET", "/me/player/currently-playing"
        )
        if resp.status_code == 204:
            return None
        if resp.status_code != 200:
            raise SpotifyApiError(
                f"now_playing failed: {resp.status_code} {resp.text}"
            )
        return resp.json()

    async def play(
        self,
        user_id: str,
        *,
        uris: list[str] | None = None,
        context_uri: str | None = None,
        device_id: str | None = None,
    ) -> None:
        target, was_active = await self._resolve_play_target(user_id, device_id)
        if not target:
            raise SpotifyNoActiveDevice(
                "No active Spotify device. Open Spotify on a phone or "
                "desktop (or play something briefly) so the device is "
                "visible to Spotify Connect, then try again."
            )

        body: dict[str, Any] = {}
        if uris:
            body["uris"] = uris
        if context_uri:
            body["context_uri"] = context_uri
        params = {"device_id": target}

        # If the device isn't currently the active one, transfer playback
        # to it first. This wakes up stale web-player tabs that show up in
        # /me/player/devices but reject play commands with "Restriction
        # violated" because their session has lapsed.
        if not was_active:
            await self._transfer_playback(user_id, target)

        resp = await self._request(
            user_id, "PUT", "/me/player/play", params=params, json=body or None
        )
        if resp.status_code in (200, 202, 204):
            return

        # Recovery path for "Restriction violated":
        # 1) Replay-same-track → seek-to-zero + resume.
        # 2) Anything else with this code → force-transfer to a fresh
        #    device candidate and retry once.
        if resp.status_code == 403 and "Restriction violated" in resp.text:
            if (
                uris
                and len(uris) == 1
                and await self._is_currently_loaded(user_id, uris[0])
            ):
                try:
                    await self.seek_to_position(user_id, 0, device_id=target)
                    resume = await self._request(
                        user_id,
                        "PUT",
                        "/me/player/play",
                        params={"device_id": target},
                    )
                    if resume.status_code in (200, 202, 204):
                        return
                except SpotifyApiError:
                    pass

            # Try once more after a force-transfer. This handles the
            # common "stale web player" case where the device shows up but
            # silently refuses play until the session is renewed.
            try:
                await self._transfer_playback(user_id, target, force=True)
            except SpotifyApiError:
                pass
            retry = await self._request(
                user_id, "PUT", "/me/player/play", params=params, json=body or None
            )
            if retry.status_code in (200, 202, 204):
                return
            raise SpotifyApiError(
                f"play failed after transfer retry: {retry.status_code} {retry.text}"
            )

        raise SpotifyApiError(f"play failed: {resp.status_code} {resp.text}")

    async def _resolve_play_target(
        self, user_id: str, device_id: str | None
    ) -> tuple[str | None, bool]:
        """Return (device_id, was_active). Caller-supplied id is treated as
        non-active (we have no cheap way to verify), so we'll always
        transfer to it first."""
        if device_id:
            return device_id, False
        devices = await self.list_devices(user_id)
        if not devices:
            return None, False
        for d in devices:
            if d.get("is_active") and not d.get("is_restricted"):
                return d["id"], True
        for d in devices:
            if not d.get("is_restricted"):
                return d["id"], False
        return devices[0]["id"], False

    async def _transfer_playback(
        self, user_id: str, device_id: str, *, force: bool = False
    ) -> None:
        """PUT /me/player to hand playback to a specific device.

        Spotify uses this to wake up a registered-but-idle device. We set
        play=false so we don't immediately autoplay whatever was last on
        that device. A subsequent /me/player/play call decides what
        actually plays.
        """
        body = {"device_ids": [device_id], "play": False}
        resp = await self._request(user_id, "PUT", "/me/player", json=body)
        if resp.status_code not in (200, 202, 204):
            if force:
                raise SpotifyApiError(
                    f"transfer failed: {resp.status_code} {resp.text}"
                )
            # Non-fatal otherwise — the subsequent play may still succeed.
            logger.warning(
                "spotify transfer to %s failed: %s %s",
                device_id,
                resp.status_code,
                resp.text,
            )

    async def seek_to_position(
        self,
        user_id: str,
        position_ms: int,
        *,
        device_id: str | None = None,
    ) -> None:
        params: dict[str, Any] = {"position_ms": max(0, int(position_ms))}
        if device_id:
            params["device_id"] = device_id
        resp = await self._request(
            user_id, "PUT", "/me/player/seek", params=params
        )
        if resp.status_code not in (200, 202, 204):
            raise SpotifyApiError(f"seek failed: {resp.status_code} {resp.text}")

    async def _is_currently_loaded(self, user_id: str, track_uri: str) -> bool:
        """Return True if `track_uri` is the track currently loaded on the
        user's player (regardless of play / pause state)."""
        try:
            now = await self.now_playing(user_id)
        except SpotifyApiError:
            return False
        if not now:
            return False
        item = now.get("item") or {}
        return item.get("uri") == track_uri

    async def pause(self, user_id: str) -> None:
        resp = await self._request(user_id, "PUT", "/me/player/pause")
        if resp.status_code not in (200, 202, 204):
            raise SpotifyApiError(f"pause failed: {resp.status_code} {resp.text}")

    async def resume(self, user_id: str) -> None:
        # /play with no body resumes whatever was last playing.
        target, was_active = await self._resolve_play_target(user_id, None)
        if not target:
            raise SpotifyNoActiveDevice("No active Spotify device.")
        if not was_active:
            await self._transfer_playback(user_id, target)
        resp = await self._request(
            user_id, "PUT", "/me/player/play", params={"device_id": target}
        )
        if resp.status_code not in (200, 202, 204):
            raise SpotifyApiError(f"resume failed: {resp.status_code} {resp.text}")

    async def skip(self, user_id: str, *, direction: str = "next") -> None:
        if direction not in ("next", "previous"):
            raise ValueError("direction must be 'next' or 'previous'")
        resp = await self._request(
            user_id, "POST", f"/me/player/{direction}"
        )
        if resp.status_code not in (200, 202, 204):
            raise SpotifyApiError(f"skip failed: {resp.status_code} {resp.text}")
