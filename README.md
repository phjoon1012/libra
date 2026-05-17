# LIBRA

A modular personal AI companion: voice conversation, memory, tools, and vision events. This README is written for developers joining the project.

**Current milestone: v0.4 (Vision)** — YOLO object detection publishes events over MQTT; the brain subscribes and logs them. Earlier milestones (v0.1–v0.3) shipped the voice shell, persistent memory, and tools (including Spotify).

| Milestone | Status | Highlights |
|-----------|--------|------------|
| v0.1 | Done | Voice UI, OpenAI Realtime + ElevenLabs+OpenAI, Docker infra |
| v0.2 | Done | Redis short-term + Postgres/pgvector memory, distiller, Memory tab |
| v0.3 | Done | Tool registry, permissions, weather/time/web_search, Spotify OAuth |
| v0.4 | Done | `services/vision`, Mosquitto, MQTT bridge (log-only) |
| v0.4.x+ | Planned | Vision UI, event persistence, Realtime tool relay |

Deep dives: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/VOICE_PROVIDERS.md`](docs/VOICE_PROVIDERS.md), [`docs/MEMORY_POLICY.md`](docs/MEMORY_POLICY.md), [`docs/TOOLS.md`](docs/TOOLS.md), [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Architecture

LIBRA uses a **central orchestrator** pattern. UI and edge devices talk to the backend; the backend talks to providers, memory, tools, and the event bus. Modules do not call each other directly.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  UI (apps/web)                                                          │
│  Dashboard · orb · transcript · settings drawer · memory tab              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP  (+ WebRTC for OpenAI Realtime audio)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Voice layer (browser)  apps/web/src/lib/voice/                           │
│  openaiRealtime.ts  |  elevenlabsOpenai.ts                                │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ POST /api/voice/session  (+ WS for EL+OAI)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Brain (apps/api)  FastAPI · routes → services → adapters                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐ │
│  │ Memory   │ │ Tools    │ │ Voice        │ │ Events (MQTT bridge)    │ │
│  │ Redis +  │ │ registry │ │ providers    │ │ vision_bridge.py        │ │
│  │ pgvector │ │ executor │ │ OpenAI / EL  │ │ subscribes libra/vision │ │
│  └──────────┘ └──────────┘ └──────────────┘ └────────────▲────────────┘ │
└──────────────────────────────────────────────────────────│──────────────┘
                                                           │
┌──────────────────────────────────────────────────────────▼──────────────┐
│  Mosquitto (infra)  port 1883 · anonymous in dev                        │
└──────────────────────────────────────────────────────────▲──────────────┘
                                                           │ MQTT publish
┌──────────────────────────────────────────────────────────┴──────────────┐
│  Vision nodes (services/vision)  Mac webcam · Jetson · future Pi cams   │
│  YOLO → on_change policy → libra/vision/{source_id}/detections            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Design rules

1. **No long-lived API keys in the browser.** OpenAI Realtime uses a short-lived `client_secret` from the backend.
2. **Routes stay thin.** Business logic lives in `apps/api/app/services/`.
3. **Swappable voice providers.** Backend: `VoiceProvider` interface. Frontend: `VoiceClient` in `lib/voice/`.
4. **Tools go through one executor.** `ToolExecutor` resolves permissions, runs the tool, returns a typed outcome.
5. **Edge services use MQTT.** Vision (and future satellites) publish events; the brain subscribes. No direct HTTP from Jetson to random API routes.

### Main request flows

| Flow | Path |
|------|------|
| **OpenAI Realtime** | Browser → `POST /api/voice/session` → backend mints session → WebRTC + data channel to OpenAI |
| **ElevenLabs + OpenAI** | Browser → session + short-lived WS token → `ws://…/api/voice/elevenlabs-openai/stream` → server STT/LLM/TTS loop |
| **Memory** | Turns → Redis buffer; recall → pgvector search; disconnect → background distiller → new facts |
| **Tools (EL+OAI only)** | LLM emits function calls → `ToolExecutor` → result fed back into Responses API (max 5 rounds) |
| **Vision** | Camera → YOLO → MQTT → `VisionEventBridge` logs to API stdout |

OpenAI Realtime does **not** have tools wired yet (v0.3.1). Use **ElevenLabs + OpenAI** to test `spotify_play`, `weather`, etc.

---

## Repository layout

```text
libra/
├── apps/
│   ├── api/                    # FastAPI brain
│   │   ├── app/
│   │   │   ├── main.py         # App factory, lifespan, CORS, logging
│   │   │   ├── core/           # config, db, redis
│   │   │   ├── api/routes/     # health, voice, memory, tools, integrations
│   │   │   ├── models/         # SQLAlchemy ORM
│   │   │   ├── schemas/        # Pydantic request/response shapes
│   │   │   ├── services/
│   │   │   │   ├── voice/      # providers, WS session, tokens
│   │   │   │   ├── memory/     # short/long term, embeddings, distiller
│   │   │   │   ├── tools/      # registry, permissions, executor, builtin/
│   │   │   │   ├── integrations/spotify/
│   │   │   │   ├── events/     # MQTT vision bridge
│   │   │   │   └── status.py   # OpenAI/EL/DB/Redis probes
│   │   │   └── tests/
│   │   ├── alembic/            # DB migrations
│   │   ├── pyproject.toml      # uv / Python 3.12+
│   │   └── Dockerfile
│   └── web/                    # Next.js 15 dashboard
│       └── src/
│           ├── app/            # layout, page
│           ├── components/libra/   # UI components
│           ├── hooks/          # useVoiceSession, useAudioDevices, …
│           ├── lib/
│           │   ├── api.ts      # typed HTTP client
│           │   ├── voice/      # provider adapters
│           │   └── audio/
│           └── types/
├── packages/
│   ├── prompts/                # LIBRA_SYSTEM_PROMPT (shared)
│   └── shared-types/           # TS types shared with web
├── services/
│   ├── vision/                 # YOLO → MQTT (runs outside Docker by default)
│   │   ├── src/libra_vision/   # camera, detector, policy, publisher, main
│   │   ├── pyproject.toml
│   │   ├── .env.example
│   │   └── README.md           # Vision-specific setup (Mac + Jetson)
│   ├── desktop-agent/          # placeholder (v0.5)
│   ├── memory/                 # placeholder
│   ├── tools/                  # placeholder
│   └── voice/                  # placeholder
├── infra/
│   ├── docker-compose.yml      # api, web, postgres, redis, mosquitto
│   ├── mosquitto/mosquitto.conf
│   └── postgres/init.sql
├── docs/                       # architecture, providers, memory, tools, roadmap
├── .env.example                # copy to .env — never commit .env
├── Makefile                    # dev, migrate, test, logs, …
└── pnpm-workspace.yaml
```

### Where to put new code

| You are building… | Put it here |
|-------------------|-------------|
| REST route | `apps/api/app/api/routes/` → thin handler |
| Business logic | `apps/api/app/services/<domain>/` |
| DB table | `apps/api/app/models/` + Alembic migration |
| API types | `apps/api/app/schemas/` |
| UI component | `apps/web/src/components/libra/` |
| Voice provider (browser) | `apps/web/src/lib/voice/` |
| Out-of-process worker | `services/<name>/` |
| Shared TS types | `packages/shared-types/` |

---

## Prerequisites

| Tool | Version | Used for |
|------|---------|----------|
| Docker + Compose | recent | Full stack (recommended) |
| Node.js | 20+ | Frontend (optional if using Docker web service) |
| pnpm | 9+ | Monorepo JS packages |
| Python | 3.12+ | API (`uv`) |
| uv | latest | API + vision package install |
| OpenAI API key | — | Voice, memory embeddings, distiller, EL+OAI |

Optional:

- **ElevenLabs** API key + voice ID — second voice provider
- **Spotify** app credentials — music tools
- **Webcam** — local vision testing (`services/vision`)

---

## Setup (recommended: Docker)

### 1. Clone and configure

```bash
git clone https://github.com/phjoon1012/libra.git
cd libra
cp .env.example .env
```

Edit `.env`. Minimum for voice:

```bash
OPENAI_API_KEY=sk-...   # required
```

For ElevenLabs + OpenAI (tools, lower-latency alternative to Realtime):

```bash
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
NEXT_PUBLIC_API_WS_BASE_URL=ws://localhost:8000
```

For Spotify (optional):

```bash
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
# Redirect URI in Spotify dashboard must be exactly:
# http://127.0.0.1:8000/api/integrations/spotify/auth/callback
```

### 2. Start the stack

```bash
make dev        # build + up: api, web, postgres, redis, mosquitto
make migrate    # first run only — apply Alembic migrations
```

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/api/health |
| MQTT broker | `localhost:1883` (plain, dev only) |

### 3. Use the dashboard

1. Open http://localhost:3000
2. **Settings** (gear) → pick provider, voice, memory toggle
3. **Connect** → allow microphone
4. Talk. Transcript appears on the right; tool chips show for EL+OAI when tools run.

After disconnect, the distiller may write facts to long-term memory (check **Memory** tab after ~3 seconds).

### Makefile commands

```bash
make dev              # start full stack
make down             # stop containers
make logs             # tail all service logs
make ps               # container status
make restart          # restart services
make build            # rebuild images
make migrate          # alembic upgrade head
make migrate-create m="describe change"   # new migration
make test             # pytest in api container
make fmt              # ruff (api) + prettier (web)
make api-shell        # shell into api container
make db-shell         # psql into postgres
make web-install      # pnpm install inside web container (if deps missing)
```

---

## Running without Docker

Useful when debugging one layer at a time. You still need Postgres, Redis, and Mosquitto running (easiest: `docker compose -f infra/docker-compose.yml up postgres redis mosquitto -d`).

### Backend

```bash
cd apps/api
uv sync
# Point DATABASE_URL / REDIS_URL / LIBRA_MQTT_HOST at localhost if not using compose service names
export DATABASE_URL=postgresql+psycopg://libra:libra@localhost:5432/libra
export REDIS_URL=redis://localhost:6379/0
export LIBRA_MQTT_HOST=127.0.0.1
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
pnpm install          # from repo root
pnpm --filter @libra/web dev
```

Ensure `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `.env`.

### Vision service (host machine, not in compose)

```bash
cd services/vision
cp .env.example .env
uv sync
uv run libra-vision
```

See [`services/vision/README.md`](services/vision/README.md) for Mac camera permissions, Jetson setup, and MQTT host configuration.

---

## Vision (v0.4)

Vision runs as a **separate Python process** on any machine with a camera. It publishes to MQTT; the API container subscribes.

```text
webcam/Jetson  →  libra-vision  →  MQTT  →  api (vision_bridge)  →  logs
```

**Topics**

| Topic | Purpose |
|-------|---------|
| `libra/vision/{source_id}/detections` | JSON event when scene changes |
| `libra/vision/{source_id}/status` | Retained `online` / `offline` (LWT) |

**Quick test (Mac)**

```bash
# Terminal 1 — stack must be up (mosquitto + api)
make dev

# Terminal 2 — vision
cd services/vision && cp .env.example .env && uv sync && uv run libra-vision

# Terminal 3 — watch MQTT
docker compose -f infra/docker-compose.yml exec mosquitto \
  mosquitto_sub -h localhost -t 'libra/vision/#' -v

# Terminal 4 — watch brain
make logs   # filter for "vision event"
```

**Jetson / remote camera:** set `LIBRA_VISION_MQTT_HOST=<Mac LAN IP>` and a unique `LIBRA_VISION_SOURCE_ID`. Open port 1883 on the Mac firewall if needed.

---

## API surface (quick reference)

| Prefix | Purpose |
|--------|---------|
| `GET /api/health` | Liveness |
| `GET /api/status` | OpenAI, ElevenLabs, Postgres, Redis probes |
| `GET/POST /api/voice/*` | Providers, session, turn capture, end, WS stream |
| `GET/POST/DELETE /api/memory/*` | Facts CRUD, search, sessions debug |
| `GET/POST /api/tools/*` | List tools, execute, permissions |
| `GET /api/integrations/spotify/*` | OAuth, status, disconnect |

Full OpenAPI: http://localhost:8000/docs

---

## Development notes

### Voice providers

| Provider | Tools | Memory recall | Notes |
|----------|-------|---------------|-------|
| OpenAI Realtime | No (yet) | Yes | WebRTC, lowest latency feel |
| ElevenLabs + OpenAI | Yes | Yes | Use for Spotify, weather, web search |

### Database migrations

Always run inside the api container (or with matching `DATABASE_URL`):

```bash
make migrate
make migrate-create m="add foo table"
```

### Adding a tool

1. Implement `Tool` subclass in `apps/api/app/services/tools/builtin/`
2. Register in `builtin/__init__.py`
3. Tool appears in LLM tool list for EL+OAI automatically
4. Document in `docs/TOOLS.md`

### Project rules

See [`.cursor/rules/libra.mdc`](.cursor/rules/libra.mdc) for coding conventions: no secrets in git, orchestrator flow, don't implement future milestones unless asked.

---

## Troubleshooting

### Docker / stack

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `port is already allocated` | Old containers from another project | `docker compose -p libra -f infra/docker-compose.yml down` or stop conflicting services |
| Web build fails `ERR_PNPM_*` | Stale `node_modules` volume | `make web-install` then restart web |
| `relation "facts" does not exist` | Migrations not applied | `make migrate` |
| API won't start, waits on mosquitto | Broker not healthy | `docker compose -f infra/docker-compose.yml logs mosquitto` |

### Voice / WebRTC

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Stuck on "Negotiating session" | Mic permission or wrong origin | Use http://localhost:3000 (not LAN IP); check browser console; allow mic |
| `Failed to fetch` on connect | API down or CORS | Check http://localhost:8000/api/health; verify `LIBRA_CORS_ORIGINS` |
| OpenAI Realtime 502 | Bad API key or model access | Check `make logs` for upstream body; verify `OPENAI_API_KEY` |
| No sound (Realtime) | AudioContext suspended | Click Connect again; check output device in Settings |
| EL+OAI WS fails | Wrong WS URL | Set `NEXT_PUBLIC_API_WS_BASE_URL=ws://localhost:8000` |
| Orb only pulses once | WebRTC + Web Audio quirk | Known issue — audio routes through AnalyserNode; reconnect |

### Memory

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Memory tab empty after chat | Distiller found 0 facts (short chat) | Talk longer; or `POST /api/memory/sessions/{id}/distill` |
| Assistant ignores stored name | Stale session or Realtime overwriting prompt | Disconnect/reconnect; Realtime should not send duplicate `session.update` |
| Facts wrong / outdated | Old distillation | Delete fact in Memory tab |

### Tools / Spotify

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Assistant says it can't use tools | On OpenAI Realtime | Switch to ElevenLabs + OpenAI in Settings |
| Assistant pretends to play music | Tool not called (Realtime) or stale memory fact | Use EL+OAI; delete wrong facts in Memory tab |
| Spotify `state_mismatch` on connect | localhost vs 127.0.0.1 cookie issue | Fixed via Redis state — pull latest; use redirect URI on 127.0.0.1 |
| Spotify 403 owner Premium | Dev app owner account not Premium | Upgrade owner account at developer.spotify.com or wait for propagation |
| `spotify_play` succeeds, no audio | No active Spotify Connect device | Open https://open.spotify.com in Chrome; play 1s; leave tab open |
| Play same song 403 Restriction | Spotify quirk on re-play | Pull latest — seek-to-zero retry in service |
| Tool chips missing | Not on EL+OAI | Switch provider |

### Vision / MQTT

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Could not open camera source: 0` | macOS camera permission denied | System Settings → Privacy → Camera → enable Terminal/Cursor; rerun |
| Vision runs but no log in API | Bridge disabled or wrong host | `LIBRA_VISION_ENABLED=true`; API uses `LIBRA_MQTT_HOST=mosquitto` in Docker |
| No events while sitting in frame | `on_change` policy | Normal — walk out and back in; or set `LIBRA_VISION_POLICY=throttled` |
| Jetson can't publish | Firewall / wrong IP | `LIBRA_VISION_MQTT_HOST=<Mac LAN IP>`; allow 1883 |
| `device=mps` fails on Intel Mac | No Apple GPU | Set `LIBRA_VISION_DEVICE=cpu` in vision `.env` |

### Logs worth knowing

```bash
make logs                              # everything
docker compose -f infra/docker-compose.yml logs api -f | grep -i vision
docker compose -f infra/docker-compose.yml logs api -f | grep -i distill
docker compose -f infra/docker-compose.yml logs api -f | grep -i spotify
```

---

## Security (development)

- **Never commit `.env`.** Only `.env.example` is tracked.
- Browser must not receive `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, or `SPOTIFY_CLIENT_SECRET`.
- MQTT broker is **anonymous** in dev. Add auth + TLS before exposing beyond localhost/LAN.
- Postgres and Redis bind to localhost in compose — do not expose on a public network without hardening.
- Real-world actions (future) require explicit permission; v0.3 Spotify consent = OAuth connect.

---

## Testing

```bash
make test    # runs pytest inside api container
```

Add service tests under `apps/api/app/tests/`. Keep smoke tests for health, tokens, and critical paths.

---

## Contributing workflow

1. Branch from `main`
2. `cp .env.example .env` locally — never commit secrets
3. `make dev && make migrate`
4. Make focused changes; update `docs/` if architecture or env vars change
5. `make test` and manual smoke (Connect, one tool call, vision if touched)
6. Open PR with what/why; link roadmap item if applicable

---

## License / contact

Internal project — coordinate with the repo owner for access and deployment targets.

For milestone status and what's intentionally not built yet, see [`docs/ROADMAP.md`](docs/ROADMAP.md).
