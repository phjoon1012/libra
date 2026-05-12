# LIBRA

A modular personal AI companion.

**v0.1 milestone:** conversational voice shell. Futuristic dashboard, swappable
voice providers, FastAPI orchestrator, and Dockerized infra. Memory, tools,
desktop control, smart home, and vision come later.

---

## Stack

| Layer       | Tech                                                    |
| ----------- | ------------------------------------------------------- |
| Frontend    | Next.js 15 (App Router), TypeScript, Tailwind CSS       |
| Backend     | FastAPI, Python 3.12, Pydantic v2, `uv` for packaging   |
| Voice (v0.1)| OpenAI Realtime via browser WebRTC                      |
| DB          | Postgres 16 + `pgvector` (extension pre-enabled)        |
| Cache/bus   | Redis 7                                                 |
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
make logs     # tail logs
make down     # stop everything
```

- Web: <http://localhost:3000>
- API: <http://localhost:8000/api/health>
- Docs: <http://localhost:8000/docs>

Click **Connect** in the dashboard, allow mic access, and start talking.

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

- **v0.2** persistent memory (Postgres + pgvector, Redis short-term)
- **v0.3** tool execution behind a permission layer
- **v0.4** desktop automation
- **v0.5** Home Assistant integration
- **v0.6** Raspberry Pi voice satellites
- **v0.7** Jetson / on-device vision

Until those land, the `services/` folders are just placeholders.
