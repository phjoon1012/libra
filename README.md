# LIBRA

A modular personal AI companion.

**Current milestone — v0.3:** tools. Backend tool registry with a permission
layer, server-orchestrated tool-call loop inside the EL+OAI streaming pipeline,
inline tool-call rendering in the transcript, and a full Spotify integration
(OAuth, transport controls, search, now-playing). Built-in `current_time` and
`weather` ship out of the box; OpenAI's hosted `web_search` is wired in too.

**v0.2** delivered: persistent memory (Postgres + pgvector, Redis short-term,
end-of-session distillation, Memory view, per-session toggle).

**v0.1** delivered: conversational voice shell, swappable voice providers,
FastAPI orchestrator, and Dockerized infra.

Future: OpenAI Realtime tool relay, approval-await UX, desktop control, smart
home, satellites, vision.

---

## Stack

| Layer       | Tech                                                    |
| ----------- | ------------------------------------------------------- |
| Frontend    | Next.js 15 (App Router), TypeScript, Tailwind CSS       |
| Backend     | FastAPI, Python 3.12, Pydantic v2, `uv` for packaging   |
| Voice       | OpenAI Realtime (WebRTC) or ElevenLabs + OpenAI (WS)    |
| DB          | Postgres 16 + `pgvector`, SQLAlchemy 2 async, Alembic   |
| Cache/bus   | Redis 7 (short-term memory, future event bus)           |
| Memory      | `text-embedding-3-small` (1536d) over HNSW cosine index |
| Tools       | Server-side registry, OpenAI tool-format JSON Schemas   |
| Integrations| Spotify Web API (OAuth2 + token refresh)                |
| Infra       | Docker Compose, Makefile                                |
| Workspace   | pnpm workspaces (`apps/*`, `packages/*`)                |

## Layout

```text
apps/
  web/      Next.js dashboard
  api/      FastAPI backend
packages/
  prompts/        shared prompt strings
  shared-types/   shared TS wire types
services/         placeholders for future out-of-process services
infra/
  docker-compose.yml
  postgres/init.sql
docs/             ARCHITECTURE / VOICE_PROVIDERS / MEMORY_POLICY / ROADMAP
```

---

## Quickstart

### 1. Prerequisites

- Docker + Docker Compose
- Node 20+ and pnpm 9+ (only needed for running the frontend outside Docker)
- An OpenAI API key with Realtime access

### 2. Configure

```bash
cp .env.example .env
# then edit .env and set at minimum:
#   OPENAI_API_KEY=sk-...
#
# To also enable the ElevenLabs + OpenAI provider, add:
#   ELEVENLABS_API_KEY=...
#   ELEVENLABS_VOICE_ID=...
```

### 3. Run

```bash
make dev      # builds and starts api, web, postgres, redis
make migrate  # apply Alembic migrations (first run only)
make logs     # tail logs
make down     # stop everything
```

- Web: <http://localhost:3000>
- API: <http://localhost:8000/api/health>
- Docs: <http://localhost:8000/docs>

Click **Connect** in the dashboard, allow mic access, and start talking.

After each conversation, an end-of-session distiller extracts a few
durable facts and writes them to long-term memory. The **Memory** tab
in the dashboard lets you search, add, and delete entries. Disable the
Memory toggle in Settings to opt the current session out entirely.

### Running pieces outside Docker

Backend only:

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

Frontend only:

```bash
pnpm install
pnpm --filter @libra/web dev
```

---

## Security notes

- **Never** commit `.env`. Only `.env.example` is tracked.
- The browser never receives `OPENAI_API_KEY`. The backend mints a short-lived
  `client_secret` from `POST /v1/realtime/sessions` and the browser uses that
  for the WebRTC handshake only.
- The dev `docker-compose.yml` binds Postgres (`5432`) and Redis (`6379`) to
  `localhost`. If you ever expose this host on a LAN/VPN, lock those down.
- All future real-world actions (messaging, smart home, desktop, purchases)
  will go through an explicit permission layer. v0.1 has none of those.

---

## What's next

See `docs/ROADMAP.md`. Short version:

- **v0.3** tool execution behind a permission layer
- **v0.4** desktop automation
- **v0.5** Home Assistant integration
- **v0.6** Raspberry Pi voice satellites
- **v0.7** Jetson / on-device vision

Until those land, the `services/` folders are just placeholders.
