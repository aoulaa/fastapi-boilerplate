"""Example module wiring — copy this shape for new modules.

Routers stay thin: resolve dependencies, call one service function, return.
No queries, no business rules, no commits here.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.items import service
from app.items.constants import ItemStatus
from app.items.dependencies import valid_item
from app.items.models import Item
from app.items.schemas import ItemCreate, ItemResponse, ItemUpdate
from app.pagination import PaginationParams, pagination
from app.schemas import PaginatedResponse
from app.user.models import User

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ItemResponse])
async def list_items(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
    page: PaginationParams = Depends(pagination),
    search: str | None = Query(default=None, min_length=1),
    item_status: ItemStatus | None = Query(default=None, alias="status"),
) -> dict:
    items = await service.list_for_owner(
        db, user.id, limit=page.limit, offset=page.offset, search=search, status=item_status
    )
    total = await service.count_for_owner(db, user.id, search=search, status=item_status)
    return {"items": items, "total": total}


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> Item:
    return await service.create(db, user, data)


@router.get("/{resource_id}", response_model=ItemResponse)
async def get_item(item: Item = Depends(valid_item)) -> Item:
    return item


@router.patch("/{resource_id}", response_model=ItemResponse)
async def update_item(
    data: ItemUpdate,
    item: Item = Depends(valid_item),
    db: AsyncSession = Depends(get_db),
) -> Item:
    return await service.update(db, item, data)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item: Item = Depends(valid_item),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete(db, item)
