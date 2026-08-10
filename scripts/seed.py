"""Idempotent reference-data seed. Safe to run on every deploy.

Every `seed_*` helper checks before inserting, so this runs as a compose step
ahead of the app and as a fallback in the test fixtures. Add new reference data
as another helper here rather than as a data migration — migrations run once,
seeds run every deploy and self-heal.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.logging import setup_logging
from app.models import import_all_models
from app.user.constants import Role
from app.user.models import User

import_all_models()

logger = logging.getLogger("seed")

# Replace with your own reference data.
DEMO_USERS: list[tuple[str, str, Role]] = [
    ("+998900000000", "Superuser", Role.ADMIN),
]


async def seed_users(db: AsyncSession) -> int:
    created = 0
    for phone, full_name, role in DEMO_USERS:
        exists = await db.execute(select(User.id).where(User.phone_number == phone))
        if exists.scalar_one_or_none():
            continue
        db.add(User(phone_number=phone, full_name=full_name, role=role))
        created += 1
    return created


async def main() -> None:
    setup_logging()
    async with async_session_maker() as db:
        created = await seed_users(db)
        await db.commit()
    logger.info("seed complete — %d user(s) created", created)


if __name__ == "__main__":
    asyncio.run(main())
