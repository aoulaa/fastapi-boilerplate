"""User persistence.

Service functions own transactions (they commit); routers never do. Every
function takes the session first so it can be composed inside a larger unit of
work by passing the same session.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.constants import Role
from app.user.exceptions import DuplicatePhone
from app.user.models import User
from app.user.schemas import UserAdminUpdate, UserCreate, UserUpdate


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_by_phone(db: AsyncSession, phone_number: str) -> User | None:
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, data: UserCreate) -> User:
    user = User(phone_number=data.phone_number, full_name=data.full_name, role=data.role)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Unique violation on phone_number. Rollback so the session is reusable
        # by the exception handler / the rest of the request.
        await db.rollback()
        raise DuplicatePhone()
    await db.refresh(user)
    return user


async def get_or_create_by_phone(db: AsyncSession, phone_number: str) -> User:
    """Used by the OTP login: first successful verification creates the account.

    Races (two devices verifying the same OTP simultaneously) land on the unique
    index; the loser re-reads the winner's row instead of failing the login.
    """
    existing = await get_by_phone(db, phone_number)
    if existing:
        return existing

    user = User(phone_number=phone_number)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raced = await get_by_phone(db, phone_number)
        if raced is None:
            raise DuplicatePhone()
        return raced
    await db.refresh(user)
    return user


async def update(db: AsyncSession, user: User, data: UserUpdate | UserAdminUpdate) -> User:
    # exclude_unset: a field the client didn't send must stay untouched, which
    # is not the same as sending an explicit null.
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


async def set_password_hash(db: AsyncSession, user: User, password_hash: str) -> User:
    user.password_hash = password_hash
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate(db: AsyncSession, user: User) -> None:
    """Soft-lock the account. Callers should also revoke the user's sessions."""
    user.is_active = False
    await db.commit()


async def soft_delete(db: AsyncSession, user: User) -> None:
    user.is_deleted = True
    await db.commit()


def _search_filter(search: str) -> ColumnElement[bool]:
    pattern = f"%{search}%"
    return or_(User.phone_number.ilike(pattern), User.full_name.ilike(pattern))


async def list_users(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    search: str | None = None,
    role: Role | None = None,
) -> Sequence[User]:
    stmt = select(User)
    if search:
        stmt = stmt.where(_search_filter(search))
    if role:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


async def count_users(db: AsyncSession, *, search: str | None = None, role: Role | None = None) -> int:
    stmt = select(func.count()).select_from(User)
    if search:
        stmt = stmt.where(_search_filter(search))
    if role:
        stmt = stmt.where(User.role == role)
    result = await db.execute(stmt)
    return int(result.scalar_one())
