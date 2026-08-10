"""Background jobs owned by the auth module."""

import logging

from app.auth import service
from app.database import async_session_maker

logger = logging.getLogger(__name__)


async def purge_dead_sessions(ctx: dict) -> int:
    """Delete session rows expired or revoked more than 30 days ago.

    Sessions are kept for a while after revocation so "where am I logged in"
    history stays meaningful; past that they're only bloat.
    """
    async with async_session_maker() as db:
        deleted = await service.purge_dead_sessions(db)
    if deleted:
        logger.info("purged %d dead sessions", deleted)
    return deleted
