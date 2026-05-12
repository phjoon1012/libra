# Memory policy

LIBRA ships **persistent memory** starting in v0.2. This document
describes what is stored, where it lives, and the policy rules around
visibility, recall, and deletion.

## Goals

- **Short-term memory:** rolling conversation context per session,
  cheap and ephemeral.
- **Long-term memory:** durable semantic memory across sessions,
  retrievable by similarity.
- **User control:** the user can inspect, search, add, and delete
  anything stored about them.

## Backends

| Layer        | Store                | Purpose                                          |
| ------------ | -------------------- | ------------------------------------------------ |
| Short-term   | Redis (list per id)  | Raw conversation turns, rolling window, 1h TTL   |
| Long-term    | Postgres + pgvector  | Distilled facts with 1536-dim embeddings (HNSW)  |

Schema (Alembic revision `0001`):

- `sessions` — one row per voice session (`id`, `user_id`, `provider`,
  `started_at`, `ended_at`, `distilled_at`).
- `facts` — durable distilled facts (`id`, `user_id`, `content`,
  `importance 1..5`, `embedding`, `source_session_id`,
  `last_recalled_at`).

## What gets stored where

- **Raw turns are NOT persisted.** They live in Redis short-term
  storage for the session and are cleared after distillation completes.
- **Only distilled facts** are written to Postgres long-term storage.
  The distiller is an LLM call that extracts a small number (0–6) of
  durable, useful facts about the user from the session transcript.
- Each fact carries an embedding produced by
  `text-embedding-3-small` (1536 dims). Vector search uses cosine
  distance over an HNSW index.

## When recall happens

1. **At session start** (both providers): the most recent N facts are
   prepended to the system prompt as baseline context. This is a
   broad "what the assistant knows about you" prelude.
2. **Per turn** (ElevenLabs+OpenAI orchestrator only): the latest user
   utterance is embedded and used to semantically search facts; the
   top-K hits are injected as an extra system message **only for that
   LLM call**, not retained in history.

The OpenAI Realtime provider runs entirely browser↔OpenAI and does not
have a server-side turn loop, so it gets baseline recall only.

## When distillation happens

- Triggered when a session ends:
  - **EL+OAI**: when the WebSocket closes (browser disconnect, server
    cancel, or error path).
  - **OpenAI Realtime**: when the browser explicitly POSTs
    `/api/voice/session/{id}/end` (the client does this on disconnect).
- Distillation runs as an async background task. The voice loop is
  never blocked.
- The distiller is given the session's transcript and asked for facts
  that will plausibly still be true and useful in future conversations.
  Small talk and one-offs are explicitly excluded.

## Policy rules

1. **No silent writes outside of distillation.** Long-term writes only
   happen via either (a) the end-of-session distiller, or (b) explicit
   user action through the Memory panel.
2. **Visibility.** The dashboard's Memory tab lists every long-term
   fact and supports search and one-click deletion.
3. **Forgetting.** Deletion is a hard delete. `DELETE /api/memory/facts/{id}`
   removes the row immediately.
4. **Disabling memory.** The Settings panel exposes a "Memory" toggle.
   When off, the session: skips baseline + per-turn recall, skips turn
   capture into Redis, and skips end-of-session distillation. Existing
   stored facts are unaffected.
5. **Provider isolation.** Recalled facts are part of the system prompt
   sent to whichever provider is active for the current session. The
   user explicitly chooses that provider before connecting.
6. **Single-user assumption.** v0.2 uses a single `user_id` (default
   `default`, overridable via `LIBRA_MEMORY_DEFAULT_USER_ID`). The
   schema includes `user_id` columns from day one so multi-user can
   land without a destructive migration.

## Tunables

All under `Settings` in `apps/api/app/core/config.py`:

| Env var | Default | Purpose |
| ------- | ------- | ------- |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Fact + recall embedding model |
| `LIBRA_EMBEDDING_DIM` | `1536` | Must match `Vector(N)` in schema |
| `LIBRA_MEMORY_SHORT_TERM_MAX_TURNS` | `40` | Redis rolling window length |
| `LIBRA_MEMORY_RECALL_TOP_K` | `5` | Per-turn semantic top-K |
| `LIBRA_MEMORY_DEFAULT_USER_ID` | `default` | Stand-in until multi-user lands |
| `LIBRA_MEMORY_DISTILL_MODEL` | `gpt-4.1-mini` | Model used by the distiller |

## API surface

- `GET    /api/memory/status` — current backends + config snapshot.
- `GET    /api/memory/facts?limit=…&offset=…` — list facts.
- `POST   /api/memory/facts` — manually add a fact.
- `POST   /api/memory/search` — semantic search (`{query, topK}`).
- `DELETE /api/memory/facts/{id}` — forget one fact.
- `DELETE /api/memory/facts` — forget everything for a user (destructive).

Voice-bound:

- `POST /api/voice/session` — also mints a `sessionId` and primes
  recall context.
- `POST /api/voice/session/{id}/turn` — record one turn (used by OpenAI
  Realtime browser client).
- `POST /api/voice/session/{id}/end` — close session + schedule distill.
