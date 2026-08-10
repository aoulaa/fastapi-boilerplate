"""Counts SQL statements per request and returns them in `X-DB-Query-Count`.

Debug environments only — the cheapest N+1 detector there is: watch the header
while clicking through the UI, and any list endpoint whose count scales with
row count is a missing `selectinload`.
"""

import logging
from contextvars import ContextVar

from sqlalchemy import event
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.database import engine

logger = logging.getLogger("app.query_counter")

_query_count: ContextVar[int | None] = ContextVar("query_count", default=None)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _count_query(
    conn: object,
    cursor: object,
    statement: str,
    parameters: object,
    context: object,
    executemany: bool,
) -> None:
    count = _query_count.get()
    if count is not None:  # None = outside a counted request (worker, startup)
        _query_count.set(count + 1)


class QueryCounterMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _query_count.set(0)
        method = scope.get("method", "")
        path = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                count = _query_count.get() or 0
                headers = list(message.get("headers", []))
                headers.append((b"x-db-query-count", str(count).encode("latin-1")))
                message["headers"] = headers
                logger.info("%s %s — %d queries", method, path, count)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _query_count.reset(token)
