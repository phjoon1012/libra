# Roadmap

This file tracks milestones honestly. A milestone is "complete" only
when the corresponding code runs, env vars are documented, Docker still
makes sense, and the relevant doc is updated.

## v0.1 — Conversational shell  *(current)*

- [x] Monorepo scaffold (`apps/`, `packages/`, `services/`, `infra/`, `docs/`)
- [x] FastAPI backend with health + provider session routes
- [x] Pydantic settings + provider registry abstraction
- [x] Next.js dashboard with LIBRA-style UI
  - [x] Audio orb / reactive visualizer (CSS, not amplitude-driven yet)
  - [x] Provider switcher
  - [x] Connection state badge
  - [x] Settings panel (voice, instructions)
  - [x] Transcript panel
  - [x] Connect / Disconnect / Mute / Interrupt
- [x] OpenAI Realtime provider over browser WebRTC
- [x] ElevenLabs + OpenAI provider stub
- [x] Docker Compose (api, web, postgres+pgvector, redis)
- [x] Makefile dev commands
- [x] Backend smoke tests (`pytest`)
- [x] README + ARCHITECTURE + VOICE_PROVIDERS + MEMORY_POLICY + ROADMAP

## v0.2 — Persistent memory

- [ ] Short-term memory in Redis (rolling turn window per session)
- [ ] Long-term memory in Postgres + pgvector
- [ ] "Memory" view in the dashboard (list, search, delete)
- [ ] Summarization worker for long sessions
- [ ] Real `/api/memory/*` routes replacing the placeholder

## v0.3 — Tools

- [ ] Tool registry on the backend
- [ ] Permission layer: every real-world action requires an explicit grant
- [ ] First tools: web search, fetch URL, simple file read
- [ ] UI: tool approval / denial flow

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
