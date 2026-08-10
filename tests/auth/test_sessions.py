import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.constants import SESSION_BLOCKLIST_PREFIX
from app.auth.exceptions import SessionNotFound, SessionRevoked
from app.auth.schemas import DeviceInfo
from app.user.models import User

DEVICE = DeviceInfo(device_name="pytest", platform=None, app_version="1.0.0")


async def test_create_session_returns_raw_token_once(db_session: AsyncSession, user: User) -> None:
    session, raw = await service.create_session(db_session, user.id, DEVICE)
    assert raw
    # Only the hash is persisted — a DB leak must not be replayable.
    assert session.refresh_token_hash != raw
    assert len(session.refresh_token_hash) == 64


async def test_rotate_invalidates_the_old_token(db_session: AsyncSession, user: User) -> None:
    _, raw = await service.create_session(db_session, user.id, DEVICE)
    _, new_raw = await service.rotate_session(db_session, raw)
    assert new_raw != raw
    with pytest.raises(SessionNotFound):
        await service.rotate_session(db_session, raw)


async def test_revoked_session_cannot_refresh(db_session: AsyncSession, redis: Redis, user: User) -> None:
    session, raw = await service.create_session(db_session, user.id, DEVICE)
    await service.revoke_session(db_session, session.id, user.id, redis)
    with pytest.raises(SessionRevoked):
        await service.rotate_session(db_session, raw)


async def test_revoke_blocklists_live_access_tokens(db_session: AsyncSession, redis: Redis, user: User) -> None:
    session, _ = await service.create_session(db_session, user.id, DEVICE)
    await service.revoke_session(db_session, session.id, user.id, redis)
    assert await redis.exists(f"{SESSION_BLOCKLIST_PREFIX}{session.id}")


async def test_revoke_all_and_listing(db_session: AsyncSession, redis: Redis, user: User) -> None:
    await service.create_session(db_session, user.id, DEVICE)
    await service.create_session(db_session, user.id, DEVICE)
    assert len(await service.list_sessions(db_session, user.id)) == 2

    assert await service.revoke_all_sessions(db_session, user.id, redis) == 2
    assert await service.list_sessions(db_session, user.id) == []


async def test_cannot_revoke_another_users_session(
    db_session: AsyncSession, redis: Redis, user: User, admin: User
) -> None:
    session, _ = await service.create_session(db_session, user.id, DEVICE)
    with pytest.raises(SessionNotFound):
        await service.revoke_session(db_session, session.id, admin.id, redis)
