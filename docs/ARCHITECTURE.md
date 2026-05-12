# Architecture

This document describes the v0.1 system and the conceptual layers
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
   │  Memory   │  │   Tools     │  │   Voice   │  │ Event/Bus   │
   │ (v0.2 +)  │  │  (v0.3 +)   │  │ Providers │  │ (Redis +)   │
   └───────────┘  └─────────────┘  └───────────┘  └─────────────┘
                                         │
                                         │ ephemeral client_secret
                                         ▼
                                  OpenAI Realtime
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
   `POST /v1/realtime/sessions`, and returns `{ clientSecret, model,
   voice, realtimeUrl, expiresAt }`.
3. Browser opens `RTCPeerConnection`, attaches the mic track, creates a
   data channel, generates an SDP offer.
4. Browser POSTs the SDP to `https://api.openai.com/v1/realtime?model=...`
   with `Authorization: Bearer <clientSecret>`.
5. Browser sets OpenAI's SDP answer as the remote description; remote
   audio track is wired to an `<audio>` element.
6. Realtime events (transcripts, response state) arrive on the data
   channel and flow to React state via `useVoiceSession`.

## Backend module map

```text
apps/api/app/
  main.py                 FastAPI app factory, CORS, route mounting
  core/config.py          Pydantic settings (env-driven)
  api/routes/
    health.py             /api/health, /api/ready
    voice.py              /api/voice/providers, /api/voice/session
    memory.py             placeholder
    tools.py              placeholder
  schemas/voice.py        Wire shapes (mirrors @libra/shared-types)
  services/voice/
    base.py               VoiceProvider ABC + errors
    registry.py           id -> provider instance
    openai_realtime.py    real provider
    elevenlabs_openai.py  stub provider
  services/memory/*       placeholder for v0.2
  services/tools/*        placeholder for v0.3
  tests/                  pytest smoke tests
```

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

## What we are deliberately not doing in v0.1

- No persistent memory. The memory route returns a placeholder.
- No tool execution. The tools route returns a placeholder.
- No desktop/browser automation, smart home, Pi satellite, or vision.
- No auth/user model. Single-user, local-only.

When any of these change, update this file.
