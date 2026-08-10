"""The global soft-delete filter is invisible at the call site, which is exactly
why it needs tests — a regression here silently resurrects deleted rows."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.items.models import Item
from app.user.models import User


async def test_deleted_rows_are_hidden(db_session: AsyncSession, user: User) -> None:
    item = Item(owner_id=user.id, name="Doomed")
    db_session.add(item)
    await db_session.commit()

    item.is_deleted = True
    await db_session.commit()
    db_session.expunge_all()

    result = await db_session.execute(select(Item).where(Item.name == "Doomed"))
    assert result.scalar_one_or_none() is None


async def test_include_deleted_escape_hatch(db_session: AsyncSession, user: User) -> None:
    item = Item(owner_id=user.id, name="Doomed", is_deleted=True)
    db_session.add(item)
    await db_session.commit()
    db_session.expunge_all()

    result = await db_session.execute(select(Item).where(Item.name == "Doomed").execution_options(include_deleted=True))
    assert result.scalar_one_or_none() is not None


async def test_filter_does_not_hide_live_rows(db_session: AsyncSession, user: User) -> None:
    db_session.add(Item(owner_id=user.id, name="Alive"))
    await db_session.commit()
    db_session.expunge_all()

    result = await db_session.execute(select(Item).where(Item.name == "Alive"))
    assert result.scalar_one_or_none() is not None
