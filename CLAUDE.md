# Working in this repo

Guidance for Claude Code (and humans) working on this codebase. Read this before adding code.

## Commands

```bash
make dev              # API + worker
make lint             # ruff format + ruff --fix + mypy  (run before committing)
make test             # migrate + pytest against app_test
make test k=auth      # filter
make makemigrations m="add item table"
make check-migrations # alembic check — model/migration drift
```

## Architecture rules

**Modules are packages, not layers.** Everything about `items` lives in `app/items/`. Do not create a top-level `services/` or `models/` directory — the split is by domain, then by file role inside it.

**Routers are thin.** A route resolves dependencies, calls one service function, returns. No queries, no business rules, no `db.commit()` in a router. If a route body is longer than about ten lines, the logic belongs in `service.py`.

**Services own transactions.** Service functions take the session as their first argument and commit. That's what lets the same function be called from a router, a worker task, or a script.

**Errors are codes.** Raise a typed exception from the module's `exceptions.py` whose `DETAIL` is an UPPERCASE member of that module's `ErrorCode` enum. Never return a prose error message — clients localize from the code, and prose is not a stable contract.

**404 over 403 for other people's rows.** `owned_resource` returns not-found when a resource exists but belongs to someone else, so ids can't be enumerated. Keep that behaviour.

**Constraints belong in the database.** Uniqueness, non-negative amounts, foreign keys — declare them in `__table_args__` and let `IntegrityError` be the authority. A `SELECT` before an `INSERT` still races.

**Money is an integer** in the smallest currency unit. Never a float.

**Enums:** add the member to the `StrEnum`, and if it's stored, generate a migration. Postgres cannot use a freshly added enum value in the same transaction — `transaction_per_migration` in `migrations/env.py` is what makes that work.

## Adding a module

1. `cp -r app/items app/<name>`, rename the symbols.
2. Register the router in `app/main.py` under `/v1/<name>`.
3. `make makemigrations m="add <name>"`, read the generated migration before committing it.
4. Add tests under `tests/<name>/`.
5. `make lint && make test`.

## Adding a background job

Write it in the owning module's `tasks.py`, taking `(ctx, ...json-safe args)`. Open a session with `async_session_maker()` — `get_db` is request-scoped and unavailable in the worker. Register it in `WorkerSettings.functions`, and add a `cron(...)` entry if it's scheduled. Cron times are UTC.

## Auth notes

- Access tokens are stateless and short (15 min). Revocation works through the Redis blocklist on the session id; anything that revokes a session must write that key.
- The `role` claim in a token goes stale on a role change. `require_role` re-reads the user row — keep it that way for anything destructive.
- Never log a full phone number. Use `mask_phone`.
- The OTP lives only in Redis with a TTL. A correct code is deleted on use; exceeding the attempt limit burns it.

## Testing notes

- `tests/conftest.py` sets `POSTGRES_DB` before importing anything from `app`, because `app.database` builds the engine at import time. Adding an app import above that line silently points the suite at the dev database.
- Tests need real Postgres and Redis. Redis DB 15 is reserved for the `redis` fixture and flushed around each test.
- CHECK constraints are invisible to `alembic check`. Cover them with a test in `tests/<module>/test_constraints.py`.

## Things that look wrong but aren't

- `import_all_models()` at the top of `main.py`, `worker.py` and `migrations/env.py` — mappers must all be registered before relationships resolve, and Alembic misses tables without it.
- `eager_defaults=True` on `Base` — without it `updated_at` expires after an UPDATE and Pydantic's sync serializer triggers a lazy load outside the greenlet context, raising `MissingGreenlet`.
- `device_name` is truncated rather than rejected — a 200-char User-Agent must not 422 an otherwise valid login.
- Login returns the same error for unknown user, no-password account, and wrong password. That's deliberate: distinguishing them makes the endpoint a phone-number oracle.
