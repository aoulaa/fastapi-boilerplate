"""Item persistence + business rules.

The router does routing; every rule lives here. That split is what lets a rule
be reused from a worker task or a management script without duplicating it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.items.constants import ItemStatus
from app.items.exceptions import DuplicateItemName, ItemArchived
from app.items.models import Item
from app.items.schemas import ItemCreate, ItemUpdate
from app.user.models import User


async def get_by_id(db: AsyncSession, item_id: uuid.UUID) -> Item | None:
    """Signature matches what `owned_resource` expects: `(db, id) -> row | None`."""
    return await db.get(Item, item_id)


def _base_query(owner_id: uuid.UUID, *, search: str | None, status: ItemStatus | None) -> Select:
    stmt = select(Item).where(Item.owner_id == owner_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(Item.name.ilike(pattern), Item.description.ilike(pattern)))
    if status:
        stmt = stmt.where(Item.status == status)
    return stmt


async def list_for_owner(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    search: str | None = None,
    status: ItemStatus | None = None,
) -> Sequence[Item]:
    stmt = _base_query(owner_id, search=search, status=status)
    stmt = stmt.order_by(Item.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


async def count_for_owner(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    search: str | None = None,
    status: ItemStatus | None = None,
) -> int:
    inner = _base_query(owner_id, search=search, status=status).subquery()
    result = await db.execute(select(func.count()).select_from(inner))
    return int(result.scalar_one())


async def create(db: AsyncSession, user: User, data: ItemCreate) -> Item:
    item = Item(owner_id=user.id, **data.model_dump())
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        # The (owner_id, name) unique index is the authority, not a prior SELECT
        # — checking first would still race with a concurrent insert.
        await db.rollback()
        raise DuplicateItemName()
    await db.refresh(item)
    return item


async def update(db: AsyncSession, item: Item, data: ItemUpdate) -> Item:
    if item.status == ItemStatus.ARCHIVED and data.status != ItemStatus.DRAFT:
        # Archived rows are read-only; the only legal edit is un-archiving.
        raise ItemArchived()

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateItemName()
    await db.refresh(item)
    return item


async def delete(db: AsyncSession, item: Item) -> None:
    """Soft delete — the row stays for audit and is hidden by the global filter."""
    item.is_deleted = True
    await db.commit()
