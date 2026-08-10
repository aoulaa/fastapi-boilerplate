"""Centralised logging + Sentry wiring shared by the web and worker processes."""

from __future__ import annotations

import logging
import sys

import sentry_sdk
from sentry_sdk.integrations.arq import ArqIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings
from app.constants import Environment

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging() -> None:
    """Configure the root logger once. Idempotent."""
    root = logging.getLogger()
    if getattr(root, "_app_configured", False):
        return

    level = logging.DEBUG if settings.ENVIRONMENT == Environment.LOCAL else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root.handlers = [handler]
    root.setLevel(level)

    # Tame verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    root._app_configured = True  # type: ignore[attr-defined]


def init_sentry(*, include_arq: bool = False) -> None:
    """Initialise Sentry with all integrations. No-ops without a DSN.

    Pass ``include_arq=True`` from the worker entrypoint so background-job spans
    are reported. The web process omits it to avoid spurious instrumentation.
    """
    if not settings.SENTRY_DSN:
        return

    integrations = [
        LoggingIntegration(
            level=logging.INFO,  # breadcrumbs from INFO+
            event_level=logging.ERROR,  # send events for ERROR+
        ),
        SqlalchemyIntegration(),
        RedisIntegration(),
        AsyncioIntegration(),
    ]
    if include_arq:
        integrations.append(ArqIntegration())

    is_prod = settings.ENVIRONMENT == Environment.PRODUCTION
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT.value,
        release=settings.APP_VERSION,
        integrations=integrations,
        traces_sample_rate=0.1 if is_prod else 1.0,
        profiles_sample_rate=0.1 if is_prod else 1.0,
        send_default_pii=False,
        attach_stacktrace=True,
        max_breadcrumbs=100,
    )
