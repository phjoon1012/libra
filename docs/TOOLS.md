# Tools

LIBRA's tool layer (v0.3) lets the assistant invoke structured backend
capabilities. Every tool is declared once on the backend; the same
schema flows to whichever voice provider supports function-calling.

## Hard rules

1. **The browser never executes.** It can display tool calls and (when
   v0.3.1 lands) approve them, but the actual call always runs in the
   FastAPI backend.
2. **No silent side effects.** Every tool declares a `default_policy`
   (`autorun` / `ask` / `denied`). The executor consults the user's
   stored decisions before running anything not marked `autorun`.
3. **The voice loop never blocks on heavy work.** Tool calls happen
   inside the streaming Responses API loop with a per-turn round cap
   (`LIBRA_TOOLS_MAX_ITERATIONS`, default 5).

## What ships in v0.3.0

| Tool                  | Default  | Description                                                |
|-----------------------|----------|------------------------------------------------------------|
| `current_time`        | autorun  | Current date/time in any IANA timezone.                    |
| `weather`             | autorun  | Open-Meteo (no API key) current + today's forecast.        |
| `spotify_search`      | autorun* | Search tracks / albums / artists / playlists.              |
| `spotify_play`        | autorun* | Play a URI or free-text query on the active Connect device.|
| `spotify_pause`       | autorun* | Pause playback.                                            |
| `spotify_resume`      | autorun* | Resume playback.                                           |
| `spotify_skip`        | autorun* | Skip next / previous.                                      |
| `spotify_now_playing` | autorun* | Report the current track.                                  |

Plus OpenAI's built-in **`web_search`** (the model decides when to
search; results stream back as part of the answer). Toggle via
`LIBRA_WEB_SEARCH_ENABLED`.

\* Spotify tools are registered only when both `SPOTIFY_CLIENT_ID` and
`SPOTIFY_CLIENT_SECRET` are set. Tools themselves are autorun, but they
return a typed error if no Spotify account is linked — the act of
**connecting** Spotify in Settings is the consent signal.

## API surface

```
GET    /api/tools                       list of {name, description,
                                                  parameters, default_policy}

POST   /api/tools/execute               manual one-off execution
  body { toolName, args, userId?, sessionId?, approveOnce? }
  ->   { status: "ok"|"pending"|"denied"|"error", content, data, ... }

GET    /api/tools/permissions?userId=…  list stored grants
POST   /api/tools/permissions           upsert { toolName, scopeKey?, state }
DELETE /api/tools/permissions/{id}      revoke one row
DELETE /api/tools/permissions?userId=…  revoke everything for a user
```

## Browser <-> backend events (EL+OAI WS)

While a session is live, the orchestrator emits these JSON frames as
the LLM loop runs:

```json
{ "type": "tool_call_started",  "tool": "weather", "callId": "...",
  "args": { "location": "Paris" } }
{ "type": "tool_call_completed","tool": "weather", "callId": "...",
  "content": "Clear sky in Paris…", "data": { … }, "error": false }
{ "type": "tool_call_denied",   "tool": "spotify_play","callId": "...",
  "reason": "denied by policy" }
{ "type": "tool_call_pending",  "tool": "fetch_url", "callId": "...",
  "args": { … }, "scopeKey": "example.com",
  "note": "approval flow not implemented yet" }
```

The frontend merges `started -> completed/denied` by `callId` so each
call renders as a single transcript row.

## Permission model

`tool_permissions(user_id, tool_name, scope_key, state)`:

- `scope_key = NULL`: tool-wide rule.
- `scope_key = "spotify"` / `"example.com"` / …: tool-with-narrowing.
- Lookup precedence at execution time:
  1. exact `(user, tool, scope_key)`
  2. fall back to `(user, tool, NULL)`
  3. fall back to the tool's `default_policy` in code
- `state` is `"allow"` or `"deny"`. There's no third value — absence
  means "consult the default policy".

## Spotify integration

OAuth flow:

```
Settings → "Connect Spotify" button
  └─► GET  /api/integrations/spotify/auth/start
        Set-Cookie: libra_spotify_oauth_state=<csrf>
        302 → https://accounts.spotify.com/authorize?…
            (user approves)
        302 → /api/integrations/spotify/auth/callback?code=…&state=…
              backend verifies cookie state, exchanges code, writes
              `spotify_accounts`, redirects browser to
              SPOTIFY_POST_AUTH_REDIRECT with ?spotify=connected
```

Scopes requested:

- `user-read-private`, `user-read-email`
- `user-read-playback-state`, `user-modify-playback-state`
- `user-read-currently-playing`

Playback constraints (Spotify's, not ours):

- **Premium required** for `play`/`pause`/`resume`/`skip`. Free
  accounts will hit 403 from the Spotify API.
- An **active Connect device** must exist somewhere (desktop app, web
  player, phone, etc.). `spotify_play` will refuse with a helpful
  message if no device is visible.
- Today, LIBRA only **commands** Spotify — it doesn't host playback.
  v0.3.1 will add the Spotify Web Playback SDK so the Libra tab itself
  becomes a target device.

Token storage: plaintext in Postgres (`spotify_accounts.access_token`,
`refresh_token`). LIBRA is a single-user local deployment for now.
When multi-user lands, encrypt at rest with a per-row key. See the
`TODO(multi-user)` marker in `app/models/integrations.py`.

## Writing a new tool

```python
# apps/api/app/services/tools/builtin/my_tool.py
from app.services.tools.base import ExecutionContext, Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "What it does, plainly. The LLM reads this."
    parameters = {
        "type": "object",
        "properties": {"foo": {"type": "string"}},
        "required": ["foo"],
        "additionalProperties": False,
    }
    default_policy = "autorun"  # or "ask" / "denied"

    def scope_key_for(self, args):
        # Optional. Return e.g. a domain, a service name, …
        return None

    async def run(self, args, ctx: ExecutionContext) -> ToolResult:
        return ToolResult(content="…", data={"…": "…"})
```

Then register it in `app/services/tools/builtin/__init__.py`. If your
tool depends on env vars, gate the registration on those being set so
unconfigured installs don't advertise broken capabilities to the LLM.
