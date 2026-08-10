"""arq worker entrypoint: `arq app.worker.WorkerSettings`.

Runs as a separate process from the web app but shares the same code, settings
and DB. Anything slow, retryable, or scheduled belongs here rather than in a
request handler.

Cron times are UTC — the container clock is UTC regardless of where the server
lives. Convert local times before writing them down.
"""

import logging

from arq import cron
from arq.connections import RedisSettings

from app.auth.tasks import purge_dead_sessions
from app.config import settings
from app.items.tasks import notify_item_owner
from app.logging import init_sentry, setup_logging
from app.models import import_all_models
from app.redis import close_redis

setup_logging()
init_sentry(include_arq=True)
import_all_models()  # register every mapper — the worker imports only some models directly

logger = logging.getLogger("app.worker")


async def startup(ctx: dict) -> None:
    logger.info("arq worker starting")


async def shutdown(ctx: dict) -> None:
    await close_redis()
    logger.info("arq worker stopping")


async def healthcheck(ctx: dict) -> str:
    """Enqueue this to prove the worker is alive end to end."""
    return "ok"


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    # A job must be listed here to be enqueueable — arq resolves by name.
    functions = [
        healthcheck,
        purge_dead_sessions,
        notify_item_owner,
    ]
    cron_jobs = [
        cron(purge_dead_sessions, hour=3, minute=0),
    ]
