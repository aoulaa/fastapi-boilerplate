"""DB-level guarantees.

Alembic autogenerate is blind to CHECK constraints, so `alembic check` will
never catch one going missing from a migration — these tests are the guard.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.items.models import Item
from app.user.models import User


async def test_price_check_constraint(db_session: AsyncSession, user: User) -> None:
    db_session.add(Item(owner_id=user.id, name="Bad", price=-1))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_owner_name_unique_constraint(db_session: AsyncSession, user: User) -> None:
    db_session.add(Item(owner_id=user.id, name="Dup"))
    await db_session.commit()
    db_session.add(Item(owner_id=user.id, name="Dup"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
