-- LIBRA Postgres bootstrap.
-- pgvector is pre-installed in the pgvector/pgvector image; this just
-- enables the extension on the default database so future memory modules
-- can store embeddings without an extra migration step.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
