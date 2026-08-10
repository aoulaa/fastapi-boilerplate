# FastAPI Boilerplate

Production-shaped async FastAPI backend: modular by domain, Postgres + Alembic, Redis, an arq worker, JWT auth with rotating refresh sessions, Eskiz SMS, i18n, Docker Compose, and GitHub Actions CI/CD with SSH deploy.

Extracted from a running production codebase, so the defaults are the ones that survived contact with real traffic rather than the ones that demo well.

## Stack

| Concern | Choice |
| --- | --- |
| API | FastAPI + Pydantic v2 |
| DB | PostgreSQL 16, SQLAlchemy 2 async, Alembic |
| Cache / queue | Redis 7, arq |
| Auth | JWT access tokens + rotating refresh sessions, scrypt passwords, phone OTP |
| SMS | Eskiz.uz (stubbed when unconfigured) |
| Observability | Sentry, structured request logs, per-request query counter |
| Tooling | uv, ruff, mypy (strict on `app`), pytest, pre-commit |
| Deploy | Docker Compose + Caddy (auto-TLS), GitHub Actions |

## Quick start

```bash
cp .env.example .env          # then set JWT_SECRET: openssl rand -hex 32
make install                  # uv sync
docker compose up -d db redis # or point .env at your own Postgres/Redis
make migrate
make seed
make dev                      # API on :8000 + worker
```

Docs at `http://localhost:8000/docs`. Create an admin with `make superuser phone=+998901234567 password=hunter2000`.

Everything in Docker instead: `make up` (hot reload, ports published) or `make up-prod` (adds Caddy and TLS).

## Layout

```
app/
  config.py database.py models.py schemas.py exceptions.py    # shared core
  logging.py redis.py pagination.py i18n.py main.py worker.py
  middleware/        locale, request logging, query counter
  auth/              login, OTP, sessions, JWT
  user/              accounts, roles, ownership dependencies
  items/             example domain module — copy this shape
  eskiz/             SMS gateway client
migrations/          Alembic
scripts/             seed, superuser bootstrap
tests/
```

## The module pattern

Every domain lives in one package with the same file names, so any module is navigable without reading it first:

| File | Holds |
| --- | --- |
| `router.py` | Routes only: resolve dependencies, call one service function, return |
| `service.py` | Business rules and queries. Owns transactions — routers never commit |
| `models.py` | SQLAlchemy tables |
| `schemas.py` | Request/response Pydantic models |
| `dependencies.py` | Reusable `Depends` — ownership checks, gates |
| `constants.py` | Enums, including this module's `ErrorCode` |
| `exceptions.py` | Typed HTTP errors mapping to those codes |
| `tasks.py` | arq background jobs |

To add a module: copy `app/items/`, rename, register the router in `app/main.py`, run `make makemigrations m="add thing"`.

### Errors are codes, not sentences

Handlers raise typed exceptions whose `DETAIL` is an UPPERCASE code (`ITEM_NOT_FOUND`, `INVALID_CREDENTIALS`). The client maps codes to localized text, so the backend never guesses the caller's language and error strings stay a stable contract.

### Ownership is a dependency

`owned_resource(service.get_by_id, not_found=ItemNotFound)` fetches `{resource_id}` and 404s — not 403s — when it belongs to someone else, so the endpoint doesn't leak which ids exist. Admins bypass it. Role gates read `require_role(Role.MANAGER)` and compare rank, not equality.

### Soft delete is global

Models mixing in `SoftDeleteMixin` are filtered out of every `SELECT` by a session-level event. Nothing at the call site opts in. To see deleted rows: `.execution_options(include_deleted=True)`.

## Auth flow

```
send-otp ──► verify-otp ─┐
                         ├──► access JWT (15 min) + refresh token (1 year)
login (password) ────────┘
                              refresh ──► rotates both
                              logout  ──► revokes + Redis blocklist
```

Refresh tokens are stored as SHA-256 hashes and rotated on every use, so a stolen token dies at the legitimate client's next refresh. Access tokens are stateless, so logout also writes a short-lived Redis blocklist entry keyed on the session id — without it a logged-out token would keep working until it expired.

Rate limits, all Redis-backed: per-phone OTP cooldown, per-IP daily OTP cap, global daily OTP budget, per-phone login lockout, per-user password-change lockout.

## SMS

`app/eskiz/` wraps Eskiz.uz: bearer token cached in Redis for 25 days and shared across processes, single re-auth retry on 401, batch send, and a classifier turning the provider's free-text errors into stable `SmsErrorCode` values. With `ESKIZ_EMAIL`/`ESKIZ_PASSWORD` blank it runs in stub mode — nothing is sent, nothing raises, so local dev and CI never burn credits.

Swapping providers means replacing this one package and keeping `SmsErrorCode`.

## Background jobs

The arq worker (`app/worker.py`) shares the codebase but runs as its own process. Register a job in `WorkerSettings.functions` to make it enqueueable; add a `cron(...)` entry to schedule it. Cron times are UTC. Ships with a nightly dead-session purge.

## Tests

```bash
make test              # migrate + run against $(TEST_DB), default app_test
make test k=auth       # filter by name
```

`tests/conftest.py` retargets the DB to a throwaway database *before* app import — `app.database` builds its engine at import time, so anything later is too late. Tables are truncated after any test that wrote rows, and skipped for tests that didn't.

Because Alembic autogenerate is blind to CHECK constraints, `alembic check` in CI cannot catch one going missing; `tests/items/test_constraints.py` covers them instead.

## CI/CD

`.github/workflows/ci.yml` runs three jobs in parallel — ruff (lint + format check), mypy, and pytest against real Postgres and Redis services — then, on a push to `main` only, deploys over SSH.

The test job also runs `alembic check` to fail on model/migration drift.

Deploy needs three repo secrets — `SERVER_HOST`, `SERVER_USER`, `SSH_PRIVATE_KEY` — and the repo cloned at `~/app` on the server with a populated `.env`. It pulls, rebuilds, and prunes old images.

## i18n

Strings wrapped in `_()` are translated per request from `Accept-Language`. Workflow: `make babel-extract` → `make babel-update` → translate `locales/<lang>/LC_MESSAGES/messages.po` → `make babel-compile`. Compiled `.mo` files are gitignored and built in Docker.

## Configuration

`.env` drives everything; see `.env.example`. Settings are split per concern (`app/config.py`) with module-local settings next to their module (`app/auth/config.py`, `app/eskiz/config.py`), so a module can be lifted out without dragging unrelated config with it.

Set `JWT_SECRET` before running anything. `ENVIRONMENT=production` disables the OpenAPI schema and the query-counter middleware.
