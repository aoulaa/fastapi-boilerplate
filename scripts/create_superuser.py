"""Create (or promote) an admin account with a password.

    make superuser phone=+998901234567 password=hunter2000

Local only by default — refuses to run unless ENVIRONMENT=local, so nobody
mints an admin on production from a shell they happened to have open. Set
ALLOW_REMOTE_SUPERUSER=1 to override deliberately.
"""

import argparse
import asyncio
import logging
import os
import sys

from app.auth.schemas import validate_password
from app.auth.utils import hash_password
from app.config import settings
from app.constants import Environment
from app.database import async_session_maker
from app.logging import setup_logging
from app.models import import_all_models
from app.user import service as user_service
from app.user.constants import Role
from app.user.schemas import UserCreate

import_all_models()

logger = logging.getLogger("create_superuser")


async def main(phone: str, password: str, full_name: str | None) -> None:
    setup_logging()

    if settings.ENVIRONMENT != Environment.LOCAL and os.getenv("ALLOW_REMOTE_SUPERUSER") != "1":
        logger.error(
            "refusing to run with ENVIRONMENT=%s (set ALLOW_REMOTE_SUPERUSER=1 to override)", settings.ENVIRONMENT
        )
        sys.exit(1)

    validate_password(password)

    async with async_session_maker() as db:
        user = await user_service.get_by_phone(db, phone)
        if user is None:
            user = await user_service.create(db, UserCreate(phone_number=phone, full_name=full_name, role=Role.ADMIN))
            logger.info("created admin %s", phone)
        else:
            user.role = Role.ADMIN
            user.is_active = True
            logger.info("promoted existing user %s to admin", phone)
        await user_service.set_password_hash(db, user, hash_password(password))

    logger.info("done — id=%s", user.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or promote an admin user.")
    parser.add_argument("phone", help="E.164 phone number, e.g. +998901234567")
    parser.add_argument("password", help="Password (8-128 chars, letter + digit)")
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.phone, args.password, args.full_name))
