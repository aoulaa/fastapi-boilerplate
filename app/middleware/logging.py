"""Per-request access log + Sentry scope enrichment."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import suppress

import sentry_sdk
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

_SKIP_PATHS = {"/health", "/metrics"}


class RequestLoggingMiddleware:
    """Log every HTTP request and tag the Sentry scope with request metadata.

    Also stamps `X-Request-ID` on the response so a user-reported error can be
    traced to a log line and a Sentry event.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        status_code = 500  # default if the response never starts

        with sentry_sdk.new_scope() as sentry_scope:
            sentry_scope.set_tag("request_id", request_id)
            sentry_scope.set_tag("http.method", method)
            sentry_scope.set_tag("http.path", path)

            async def send_wrapper(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", request_id.encode()))
                    message = {**message, "headers": headers}
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                duration_ms = (time.perf_counter() - started) * 1000
                logger.exception(
                    "request failed",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                raise
            else:
                if path in _SKIP_PATHS:
                    return
                duration_ms = (time.perf_counter() - started) * 1000
                level = logging.WARNING if status_code >= 500 else logging.INFO
                logger.log(
                    level,
                    "%s %s -> %d (%.1fms)",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                with suppress(Exception):
                    sentry_sdk.add_breadcrumb(
                        category="request",
                        level="info",
                        message=f"{method} {path}",
                        data={"status": status_code, "duration_ms": round(duration_ms, 2)},
                    )
