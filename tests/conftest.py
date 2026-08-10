import os

# Point the app at a throwaway database BEFORE any app module imports, because
# `app.database` builds the engine at import time from `settings`. An OS env var
# wins over the .env value in pydantic-settings. Override with POSTGRES_DB=… to
# retarget. Without this, a test that commits would write to the dev database.
os.environ.setdefault("POSTGRES_DB", "app_test")
# ≥32 bytes: PyJWT warns below that for HS256.
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-tests-only-do-not-use-anywhere-else")

import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

from app.auth.utils import create_access_token, hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import async_session_maker, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, import_all_models  # noqa: E402
from app.user.constants import Role  # noqa: E402
from app.user.models import User  # noqa: E402

import_all_models()

TEST_PASSWORD = "hunter2000"

# Whether the current test issued any DML. The teardown TRUNCATE only has to run
# when a test actually wrote rows — read-only and pure-unit tests skip it, which
# is most of the suite and a large speedup with no loss of isolation.
_db_dirty = {"v": False}
# "WITH" covers CTE-wrapped DML. It also matches read-only CTEs, which
# over-truncates harmlessly — it never under-truncates.
_DML_PREFIXES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "COPY", "WITH")


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _mark_db_dirty(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
    if statement.lstrip()[:10].upper().startswith(_DML_PREFIXES):
        _db_dirty["v"] = True


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _db_schema() -> AsyncGenerator[None, None]:
    """Ensure the schema exists on the test DB.

    `make test` runs `alembic upgrade head` first; this is an idempotent
    fallback so a bare `pytest` still works. `create_all` uses checkfirst, so an
    already-migrated schema is left untouched.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _truncate_db(_db_schema: None) -> AsyncGenerator[None, None]:
    """Wipe every table after each test so committed rows never leak forward."""
    _db_dirty["v"] = False
    yield
    if not _db_dirty["v"]:
        return
    async with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        if tables:
            await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(loop_scope="session")
async def redis() -> AsyncGenerator[Redis, None]:
    """Real Redis on a dedicated DB index, flushed around each test."""
    client = Redis.from_url(f"{settings.REDIS_URL}/15", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(loop_scope="session")
async def db_session() -> AsyncGenerator:
    async with async_session_maker() as session:
        yield session


def _make_user(role: Role = Role.USER, *, with_password: bool = True) -> User:
    suffix = uuid.uuid4().int % 10**9
    return User(
        phone_number=f"+9989{suffix:09d}"[:14],
        full_name="Test User",
        role=role,
        password_hash=hash_password(TEST_PASSWORD) if with_password else None,
    )


@pytest_asyncio.fixture(loop_scope="session")
async def user() -> AsyncGenerator[User, None]:
    async with async_session_maker() as db:
        obj = _make_user()
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        yield obj


@pytest_asyncio.fixture(loop_scope="session")
async def admin() -> AsyncGenerator[User, None]:
    async with async_session_maker() as db:
        obj = _make_user(Role.ADMIN)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        yield obj


def auth_headers(user: User) -> dict[str, str]:
    """Bearer header for a real user row. `sid` is random — no session row is
    needed because access tokens are stateless; only the blocklist is checked."""
    token = create_access_token(str(user.id), str(uuid.uuid4()), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def auth_client(client: AsyncClient, user: User) -> AsyncGenerator[AsyncClient, None]:
    client.headers.update(auth_headers(user))
    yield client
    client.headers.pop("Authorization", None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
