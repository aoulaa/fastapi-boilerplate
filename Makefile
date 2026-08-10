.PHONY: help install dev backend worker migrate makemigrations check-migrations seed superuser \
	lint format typecheck test babel-extract babel-update babel-compile \
	up down restart logs ps up-prod down-prod logs-prod ps-prod

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Sync dependencies from uv.lock
	uv sync

dev:  ## Run API + worker together (Ctrl-C stops both)
	trap 'kill 0' SIGINT; \
	uv run uvicorn app.main:app --reload & \
	$(MAKE) worker; \
	wait

backend:  ## Run the API only, with reload
	uv run uvicorn app.main:app --reload

worker:  ## Run the arq worker
	uv run arq app.worker.WorkerSettings

migrate:  ## Apply migrations
	uv run alembic upgrade head

makemigrations:  ## Autogenerate a migration: make makemigrations m="add table"
	uv run alembic revision --autogenerate -m "$(m)"

check-migrations:  ## Fail if models and migrations disagree (CHECK constraints excluded — see tests)
	uv run alembic check

seed:  ## Insert reference data (idempotent)
	uv run python scripts/seed.py

superuser:  ## make superuser phone=+998901234567 password=hunter2000
	uv run python scripts/create_superuser.py $(phone) $(password)

lint:  ## Format, autofix, and typecheck
	uv run ruff format .
	uv run ruff check --fix .
	uv run mypy app

format:  ## Format only
	uv run ruff format .

typecheck:  ## mypy only
	uv run mypy app

# Tests run against a throwaway DB (never the dev DB) — override with TEST_DB.
# Schema comes through the real migration path so tests exercise shipped DDL.
# `make test k=foo` filters by name.
TEST_DB ?= app_test

test:  ## Run the test suite against $(TEST_DB)
	POSTGRES_DB=$(TEST_DB) uv run alembic upgrade head
	POSTGRES_DB=$(TEST_DB) uv run pytest $(if $(k),-k "$(k)",)

babel-extract:  ## Collect translatable strings into locales/messages.pot
	uv run pybabel extract -F babel.cfg -o locales/messages.pot app

babel-update:  ## Merge new strings into the per-language .po files
	uv run pybabel update -i locales/messages.pot -d locales

babel-compile:  ## Compile .po -> .mo (required before running)
	uv run pybabel compile -d locales

COMPOSE_LOCAL = docker compose -f docker-compose.yml -f docker-compose.local.yml

up:  ## Start the local stack (ports published, hot reload)
	$(COMPOSE_LOCAL) up --build

down:  ## Stop the local stack
	$(COMPOSE_LOCAL) down

restart:  ## Restart the local stack
	$(COMPOSE_LOCAL) restart

logs:  ## Tail local logs
	$(COMPOSE_LOCAL) logs -f

ps:  ## Local container status
	$(COMPOSE_LOCAL) ps

up-prod:  ## Start the production stack (includes Caddy/TLS)
	docker compose --profile prod up -d --build --remove-orphans

down-prod:  ## Stop the production stack
	docker compose --profile prod down

logs-prod:  ## Tail production logs
	docker compose --profile prod logs -f

ps-prod:  ## Production container status
	docker compose --profile prod ps
