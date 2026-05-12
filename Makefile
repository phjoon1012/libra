COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: help dev up down logs ps restart build api-shell web-shell db-shell test fmt

help:
	@echo "LIBRA dev commands:"
	@echo "  make dev        - start the full stack (api, web, postgres, redis)"
	@echo "  make down       - stop and remove containers"
	@echo "  make logs       - tail logs from all services"
	@echo "  make ps         - show running services"
	@echo "  make restart    - restart all services"
	@echo "  make build      - rebuild images"
	@echo "  make api-shell  - shell into the api container"
	@echo "  make web-shell  - shell into the web container"
	@echo "  make db-shell   - psql into the postgres container"
	@echo "  make test       - run backend tests"
	@echo "  make fmt        - format frontend and backend"

dev:
	@test -f .env || (echo ".env not found. Copy .env.example to .env first." && exit 1)
	$(COMPOSE) up --build

up: dev

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build

api-shell:
	$(COMPOSE) exec api /bin/sh

web-shell:
	$(COMPOSE) exec web /bin/sh

web-install:
	$(COMPOSE) exec web sh -c "cd /repo && pnpm install --no-frozen-lockfile"

db-shell:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-libra} -d $${POSTGRES_DB:-libra}

test:
	$(COMPOSE) exec api uv run pytest -q

fmt:
	cd apps/web && pnpm run format || true
	cd apps/api && uv run ruff format . && uv run ruff check --fix .
