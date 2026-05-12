# Roadmap

This file tracks milestones honestly. A milestone is "complete" only
when the corresponding code runs, env vars are documented, Docker still
makes sense, and the relevant doc is updated.

## v0.1 — Conversational shell

- [x] Monorepo scaffold (`apps/`, `packages/`, `services/`, `infra/`, `docs/`)
- [x] FastAPI backend with health + provider session routes
- [x] Pydantic settings + provider registry abstraction
- [x] Next.js dashboard with LIBRA-style UI
  - [x] Amplitude-driven audio orb (Three.js)
  - [x] Provider switcher
  - [x] Connection state badge
  - [x] Settings panel (voice, instructions, voice tunables, memory toggle)
  - [x] Transcript panel
  - [x] Connect / Disconnect / Mute / Interrupt
  - [x] Mic / output device selector
- [x] OpenAI Realtime provider over browser WebRTC
- [x] ElevenLabs + OpenAI fully streaming pipeline (STT / LLM / TTS)
- [x] Docker Compose (api, web, postgres+pgvector, redis)
- [x] Makefile dev commands
- [x] Backend smoke tests (`pytest`)
- [x] README + ARCHITECTURE + VOICE_PROVIDERS + MEMORY_POLICY + ROADMAP

## v0.2 — Persistent memory

- [x] Short-term memory in Redis (rolling turn window per session, 1h TTL)
- [x] Long-term memory in Postgres + pgvector (HNSW cosine index)
- [x] Alembic schema + initial migration
- [x] OpenAI `text-embedding-3-small` for fact embeddings
- [x] End-of-session distiller (background task, off the voice path)
- [x] Baseline recall on connect + per-turn semantic recall (EL+OAI)
- [x] Real `/api/memory/*` routes replacing the placeholder
- [x] Memory view in the dashboard (list, search, delete, manual add)
- [x] Memory on/off toggle per session

## v0.3 — Tools  *(current)*

### v0.3.0 — shipped

- [x] Backend tool registry (JSON-Schema tool defs, OpenAI tool format)
- [x] Permission layer: `tool_permissions` table, default-policy resolution
- [x] `/api/tools/*` routes (list, execute, permissions CRUD)
- [x] Built-in tools: `current_time`, `weather` (Open-Meteo, no API key)
- [x] OpenAI built-in `web_search` enabled in the Responses API loop
- [x] EL+OAI streaming pipeline parses function-calls, executes server-side,
      feeds outputs back, continues streaming (max 5 rounds)
- [x] Inline tool-call rows in the transcript (started → completed/denied)
- [x] Spotify integration: OAuth, token refresh, full transport tools
      (`spotify_search` / `play` / `pause` / `resume` / `skip` / `now_playing`)
- [x] Spotify connect/disconnect UI in Settings; connection IS consent
- [x] Docs + .env.example + Alembic migrations for `tool_permissions` and
      `spotify_accounts`

### v0.3.1 — next

- [ ] OpenAI Realtime tool relay (browser forwards function calls → backend)
- [ ] Approval-await loop for `default_policy="ask"` tools (chip UI)
- [ ] `fetch_url` and sandboxed `read_file`
- [ ] Spotify Web Playback SDK so the Libra tab itself is a play target

## v0.4 — Desktop control

- [ ] Local desktop agent in `services/desktop-agent`
- [ ] Pairing flow with the backend
- [ ] Safe action surface: open app, focus window, type text (gated)

## v0.5 — Home Assistant

- [ ] Home Assistant adapter behind the tool layer
- [ ] Entity discovery + per-entity permissions
- [ ] No control of locks / alarms / cameras without explicit, scoped consent

## v0.6 — Raspberry Pi voice satellite

- [ ] Wake-word + audio capture on the Pi
- [ ] Streaming audio over LAN to LIBRA core
- [ ] Multi-satellite session arbitration

## v0.7 — Jetson / on-device vision

- [ ] Local vision worker
- [ ] Scene description and presence detection events on the bus
- [ ] Privacy controls: per-camera enable, recording policy

## Cross-cutting (any version)

- [ ] AuthN/AuthZ for multi-user
- [ ] Observability (structured logs, traces)
- [ ] Hardening: CSP, rate limits, audit log
