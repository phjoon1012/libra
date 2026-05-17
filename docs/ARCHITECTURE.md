# Architecture

This document describes the v0.4 system and the conceptual layers
everything else will plug into.

## Conceptual layers

```text
   ┌────────────────────────────────────────────────────────────────┐
   │                          UI Layer                              │
   │   apps/web  (Next.js dashboard, mic capture, audio playback)   │
   └────────────────────────┬───────────────────────────────────────┘
                            │ HTTP (session config) + WebRTC (media)
   ┌────────────────────────▼───────────────────────────────────────┐
   │                 Voice Provider Layer (browser)                 │
   │   apps/web/src/lib/voice  (OpenAI Realtime, ElevenLabs stub)   │
   └────────────────────────┬───────────────────────────────────────┘
                            │ POST /api/voice/session
   ┌────────────────────────▼───────────────────────────────────────┐
   │              LIBRA Core / Backend API (FastAPI)                │
   │   apps/api/app  (routes -> services -> providers)              │
   └─────┬───────────────┬───────────────┬───────────────┬──────────┘
         │               │               │               │
   ┌─────▼─────┐  ┌──────▼──────┐  ┌─────▼─────┐  ┌──────▼──────┐
   │  Memory   │  │   Tools     │  │   Voice   │  │ Event Layer │
   │ (Redis +  │  │  (v0.3 +)   │  │ Providers │  │  (MQTT)     │
   │ pgvector) │  │             │  │           │  │             │
   └───────────┘  └─────────────┘  └───────────┘  └──────▲──────┘
                                         │              │
                                         │              │ libra/vision/+/detections
                                         ▼              │
                                  OpenAI Realtime       │
                                                ┌───────┴────────┐
                                                │ Mosquitto      │
                                                │ broker         │
                                                └───────▲────────┘
                                                        │ publish
                                          ┌─────────────┴─────────────┐
                                          │  services/vision (YOLO)   │
                                          │  Mac webcam / Jetson cam  │
                                          └───────────────────────────┘
```

Rules of the road:

- The UI never talks to providers directly with long-lived keys.
- Routes are thin. Business logic lives in `app/services`.
- Provider-specific code (OpenAI, ElevenLabs, future ones) stays behind
  the `VoiceProvider` interface in `apps/api/app/services/voice/`.
- Frontend provider-specific code stays in `apps/web/src/lib/voice/`.
- Cross-cutting wire shapes live in `packages/shared-types`.

## Request flow (OpenAI Realtime)

1. Browser POSTs `{ provider: "openai-realtime", voice, instructions }`
   to `/api/voice/session`.
2. Backend looks up the provider via the registry, calls OpenAI's
   `POST /v1/realtime/client_secrets`, and returns `{ clientSecret, model,
   voice, realtimeUrl, expiresAt }`.
3. Browser opens `RTCPeerConnection`, attaches the mic track, creates a
   data channel, generates an SDP offer.
4. Browser POSTs the SDP to `https://api.openai.com/v1/realtime/calls`
   with `Authorization: Bearer <clientSecret>`.
5. Browser sets OpenAI's SDP answer as the remote description; remote
   audio track is wired to an `<audio>` element.
6. Realtime events (transcripts, response state) arrive on the data
   channel and flow to React state via `useVoiceSession`.

## Backend module map

```text
apps/api/app/
  main.py                 FastAPI app factory, CORS, route mounting
  core/
    config.py             Pydantic settings (env-driven)
    db.py                 Async SQLAlchemy engine + session factory
    redis.py              Async Redis client
  api/routes/
    health.py             /api/health, /api/ready
    voice.py              /api/voice/* (providers, session, turn, end, WS)
    memory.py             /api/memory/* (facts CRUD + semantic search)
    tools.py              /api/tools/* (list, execute, permissions)
    integrations.py       /api/integrations/* (Spotify OAuth + status)
  models/                 SQLAlchemy ORM (sessions, facts, base,
                          tool_permissions, spotify_accounts)
  schemas/                Pydantic wire shapes (voice, memory, tools)
  services/voice/
    base.py               VoiceProvider ABC + SessionContext
    registry.py           id -> provider instance
    openai_realtime.py    WebRTC session-mint provider
    elevenlabs_openai.py  Streaming pipeline provider
    elevenlabs_openai_session.py  WS-side orchestrator (tool-aware)
    ws_tokens.py          Short-lived single-use WS auth tokens
  services/memory/
    service.py            MemoryService façade
    short_term.py         Redis rolling-window store
    long_term.py          Postgres + pgvector store
    embeddings.py         OpenAI embedding wrapper
    distiller.py          End-of-session fact extractor
  services/tools/
    base.py               Tool ABC, ToolResult/Pending/Denied, Context
    registry.py           Process-wide ToolRegistry singleton
    permissions.py        Stored permission lookup (per-tool, scoped)
    executor.py           Single execution chokepoint
    builtin/              current_time, weather, spotify_*
  services/integrations/spotify/
    service.py            OAuth + token refresh + Web API helpers
    errors.py             Typed Spotify errors
  alembic/                Migrations (env.py + versions/)
  tests/                  pytest smoke tests
```

## Memory flow (v0.2)

```text
   browser ─turn─► backend orchestrator ─append─► Redis short-term
                                            │
                                            └─per LLM call─► pgvector recall
                                                              │
                                                              ▼
                                                       extra system msg
                                            (transient, not stored in history)

   browser disconnect ─► end_session ─► async distiller task
                                            │
                                            ▼
                                  facts + embeddings → pgvector
```

See `docs/MEMORY_POLICY.md` for what is stored, when recall happens,
and the deletion / disable rules.

## Tool flow (v0.3, EL+OAI provider)

```text
   ┌─ user text from STT
   │
   ▼
LLM round (Responses API streaming, tools=[...])
   │
   ├─ text deltas ──► browser + ElevenLabs TTS (streaming)
   │
   └─ function_call items ──► ToolExecutor
                                 │
                                 ├─ permission check (autorun / ask / denied)
                                 ├─ tool.run(args, ctx)
                                 ▼
                              ToolResult ──► function_call_output
                                                 │
                                                 ▼
                                       next LLM round (previous_response_id)
                                                 │
                                                 ▼
                                           (loop, max 5 rounds)
```

Browser shows each tool call inline in the transcript via
`tool_call_started` / `tool_call_completed` / `tool_call_denied` events
on the same WebSocket. See `docs/TOOLS.md` for full details.

## Vision flow (v0.4)

Vision lives outside the main API process — `services/vision/` is its
own Python project deployable on the developer Mac OR a Jetson Nano
satellite. It pushes events through MQTT rather than calling into the
brain directly, so multiple sources can come online and offline without
coupling.

```text
[camera] ─► YOLO (Ultralytics, MPS/CUDA/CPU)
              │
              ▼
         class filter (e.g. person)
              │
              ▼
         emission policy
            (on_change | throttled | both)
              │
              ▼
         MQTT publish ─► libra/vision/{source}/detections   (per event)
                     └─► libra/vision/{source}/status       (retained;
                                                              LWT = "offline")
                              │
                              ▼
                  ┌─────────────────────────────┐
                  │ Mosquitto broker (Docker)   │
                  └─────────────────────────────┘
                              │
                              ▼
                  Brain API: VisionEventBridge subscribes,
                  logs `vision event (mac-webcam/change): 1 person …`
                  to API stdout. Future handlers (memory write,
                  in-process bus, dashboard) plug in here.
```

Topics live under `libra/vision/+/{detections,status}`. The retained
status topic plus the broker's Last-Will-and-Testament feature means
the brain always has an authoritative "is this camera alive?" view
even if a Jetson crashes or its wifi drops. See
`services/vision/README.md` for the deployable details.

## Frontend module map

```text
apps/web/src/
  app/                    App Router (layout, dashboard page, globals)
  components/
    libra/                domain components (orb, transcript, controls, ...)
    ui/                   primitives (Button)
  hooks/useVoiceSession   single hook that drives state for the page
  lib/api.ts              typed wrappers around the FastAPI endpoints
  lib/voice/
    types.ts              VoiceClient interface
    registry.ts           id -> factory
    openaiRealtime.ts     WebRTC client for OpenAI Realtime
    elevenlabsOpenai.ts   stub client
  types/voice.ts          re-exports shared types + UI-only types
```

## What we are deliberately not doing yet

- No tools wired into the OpenAI Realtime provider yet. The browser
  data-channel relay lands in v0.3.1. EL+OAI is the tool-capable path
  today.
- No approval-await loop for "ask" tools. The framework supports
  `default_policy="ask"` but the WS-side approval flow ships in v0.3.1.
  All currently-shipped tools are `autorun` (consent for Spotify is the
  OAuth connection itself).
- No `fetch_url` or `read_file` yet — both land in v0.3.1.
- Vision currently only **logs** events. No persistence, no
  memory injection, no UI surfaced — that's v0.4.x.
- No desktop/browser automation, smart home, or Pi satellite yet.
- No auth/user model. Single-user, local-only. The `facts.user_id`,
  `tool_permissions.user_id`, and `spotify_accounts.user_id` columns
  exist so multi-user can land non-destructively later.

When any of these change, update this file.
