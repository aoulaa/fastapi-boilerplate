"""Example background job.

Two things worth copying: the task opens its own session (worker jobs have no
request scope, so `get_db` is unavailable), and it takes plain JSON-safe
arguments — arq serializes them, so ORM objects can't be passed.

Enqueue from a router with:

    from arq.connections import create_pool
    from arq.connections import RedisSettings
    from app.config import settings

    pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    await pool.enqueue_job("notify_item_owner", str(item.id))
"""

import logging
import uuid

from app.database import async_session_maker
from app.eskiz import eskiz_client, record_sms_failure
from app.items import service
from app.user import service as user_service

logger = logging.getLogger(__name__)


async def notify_item_owner(ctx: dict, item_id: str) -> str:
    """SMS the owner about their item. Returns a status string for the arq log."""
    async with async_session_maker() as db:
        item = await service.get_by_id(db, uuid.UUID(item_id))
        if item is None:
            logger.info("notify_item_owner: item %s is gone, skipping", item_id)
            return "skipped"
        owner = await user_service.get_by_id(db, item.owner_id)
        if owner is None or not owner.is_active:
            return "skipped"
        phone, name = owner.phone_number, item.name

    try:
        await eskiz_client.send(phone.lstrip("+"), f"Your item '{name}' is ready.")
    except Exception as exc:
        # Swallow and record: a failed notification must not fail the job and
        # trigger arq's retry storm against a provider that's already down.
        record_sms_failure(exc, context={"flow": "item_notify", "item_id": item_id})
        return "failed"
    return "sent"
