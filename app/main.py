from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth.router import router as auth_router
from app.config import settings
from app.database import engine
from app.items.router import router as items_router
from app.logging import init_sentry, setup_logging
from app.middleware.locale import LocaleMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.query_counter import QueryCounterMiddleware
from app.models import import_all_models
from app.redis import close_redis
from app.user.router import router as user_router

# Must run before the app is built so every mapper is registered — otherwise
# relationships to modules nothing imports directly fail to resolve.
import_all_models()

setup_logging()
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Fail fast: a container that can't reach Postgres should die at boot and
    # let the orchestrator restart it, not serve 500s.
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await close_redis()
    await engine.dispose()


app_configs: dict = {
    "title": f"{settings.APP_NAME} API",
    "version": settings.APP_VERSION,
    "lifespan": lifespan,
}
if not settings.ENVIRONMENT.is_debug:
    # No public schema dump in production.
    app_configs["openapi_url"] = None

app = FastAPI(**app_configs)

# Order matters: middleware added last runs first. CORS must sit outermost so
# error responses from the inner layers still carry the CORS headers.
app.add_middleware(LocaleMiddleware)
if settings.ENVIRONMENT.is_debug:
    app.add_middleware(QueryCounterMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGINS_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=settings.CORS_HEADERS,
    expose_headers=["X-Request-ID"] + (["X-DB-Query-Count"] if settings.ENVIRONMENT.is_debug else []),
)


@app.get("/health", tags=["Health"], include_in_schema=False)
async def health() -> dict[str, str]:
    """Liveness probe. Deliberately does not touch the DB — a slow query must
    not make the orchestrator kill an otherwise healthy container."""
    return {"status": "ok"}


app.include_router(auth_router, prefix="/v1/auth", tags=["Auth"])
app.include_router(user_router, prefix="/v1/users", tags=["Users"])
app.include_router(items_router, prefix="/v1/items", tags=["Items"])
