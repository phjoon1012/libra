# Memory policy

Memory is **not implemented** in v0.1. This document captures the
intended shape so future work follows a single design.

## Goals

- **Short-term memory:** rolling conversation context per session,
  cheap and ephemeral.
- **Long-term memory:** durable semantic memory across sessions,
  retrievable by similarity and by structured filters.
- **User control:** the user can inspect, edit, and delete anything
  stored about them.

## Planned backends

| Layer        | Store            | Purpose                                      |
| ------------ | ---------------- | -------------------------------------------- |
| Short-term   | Redis            | recent turns, transient state, rate limits   |
| Long-term    | Postgres + pgvector | facts, summaries, embeddings, source refs |
| Source files | Object storage / FS | raw artifacts referenced by long-term rows |

`pgvector` is already enabled in `infra/postgres/init.sql` so v0.2 can
add tables without a migration to enable the extension.

## Policy rules

These are project rules, not implementation details. They apply as soon
as memory is real:

1. **No silent writes.** Every long-term memory write must be either
   user-initiated or summarized from a session the user explicitly held.
2. **Visibility.** A "memory" view in the dashboard must list, group,
   and allow deletion of stored items.
3. **Scoping.** Sensitive items (credentials, addresses, health, etc.)
   require explicit opt-in tags. Default is "general".
4. **Provider isolation.** Memory contents must not be sent to any
   provider that hasn't been explicitly granted access for that turn.
5. **Forgetting.** Deletion is hard delete by default. Soft delete is
   opt-in for audit cases only.

## Out of scope for v0.1

- Embedding any conversation content.
- Persisting transcripts to disk.
- Any cross-session recall.

The placeholder route `/api/memory/status` and `services/memory/placeholder.py`
exist purely so the wiring is in place for v0.2.
