-- LIBRA Postgres bootstrap.
-- pgvector is pre-installed in the pgvector/pgvector image. Enabling
-- the extensions here means a freshly-provisioned database is ready
-- before Alembic migrations run; migrations idempotently re-enable
-- them as well so this file is convenience, not a contract.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
