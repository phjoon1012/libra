"""Third-party integration routes.

Currently: Spotify OAuth + status.
"""

from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.services.integrations.spotify import (
    SpotifyAuthError,
    SpotifyNotConfigured,
    SpotifyService,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# We store the CSRF state in Redis (not a cookie) because Spotify requires
# 127.0.0.1 (not localhost) as the OAuth redirect target, so /auth/start and
# /auth/callback land on different browser-side origins. A cookie set on the
# /auth/start origin would never be sent on the /auth/callback request.
OAUTH_STATE_KEY = "libra:spotify:oauth_state:{state}"
OAUTH_STATE_TTL = 600  # 10 minutes


def _resolve_user(user_id: str | None) -> str:
    return user_id or get_settings().memory_default_user_id


# ----- Spotify --------------------------------------------------------------


@router.get("/spotify/status")
async def spotify_status(
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    svc = SpotifyService(db)
    if not svc.is_configured:
        return {"configured": False, "connected": False}
    account = await svc.get_account(_resolve_user(user_id))
    if account is None:
        return {"configured": True, "connected": False}
    return {
        "configured": True,
        "connected": True,
        "spotifyUserId": account.spotify_user_id,
        "displayName": account.display_name,
        "product": account.product,
        "scope": account.scope,
        "connectedAt": account.connected_at.isoformat(),
    }


@router.get("/spotify/auth/start")
async def spotify_auth_start(
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    svc = SpotifyService(db)
    try:
        url, state = svc.build_authorize_url()
    except SpotifyNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Park the CSRF state in Redis with a short TTL. Looked up in /callback.
    redis = get_redis()
    await redis.set(
        OAUTH_STATE_KEY.format(state=state), "1", ex=OAUTH_STATE_TTL
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/spotify/auth/callback")
async def spotify_auth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    redis = get_redis()

    def _bounce(params: dict[str, str]) -> RedirectResponse:
        sep = "&" if "?" in settings.spotify_post_auth_redirect else "?"
        url = (
            settings.spotify_post_auth_redirect + sep + urllib.parse.urlencode(params)
        )
        return RedirectResponse(url=url, status_code=302)

    if error:
        return _bounce({"spotify": "error", "reason": error})
    if not code or not state:
        return _bounce({"spotify": "error", "reason": "missing_code_or_state"})

    # Consume the state in one atomic step so a replay can't re-use it.
    stored = await redis.getdel(OAUTH_STATE_KEY.format(state=state))
    if not stored:
        return _bounce({"spotify": "error", "reason": "state_mismatch_or_expired"})

    svc = SpotifyService(db)
    try:
        await svc.link_account(
            user_id=_resolve_user(None), code=code
        )
    except (SpotifyAuthError, SpotifyNotConfigured) as exc:
        logger.exception("Spotify link failed")
        return _bounce({"spotify": "error", "reason": str(exc)[:120]})
    return _bounce({"spotify": "connected"})


@router.post("/spotify/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def spotify_disconnect(
    user_id: str | None = Query(default=None, alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = SpotifyService(db)
    await svc.disconnect(_resolve_user(user_id))
