import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.pagination import PaginationParams, pagination
from app.schemas import PaginatedResponse
from app.user import service
from app.user.constants import Role
from app.user.dependencies import require_admin
from app.user.exceptions import UserNotFound
from app.user.models import User
from app.user.schemas import UserAdminUpdate, UserCreate, UserResponse, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)) -> User:
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> User:
    return await service.update(db, user, data)


@router.get("", response_model=PaginatedResponse[UserResponse], dependencies=[Depends(require_admin)])
async def list_users(
    db: AsyncSession = Depends(get_db),
    page: PaginationParams = Depends(pagination),
    search: str | None = Query(default=None, min_length=1),
    role: Role | None = Query(default=None),
) -> dict:
    items = await service.list_users(db, limit=page.limit, offset=page.offset, search=search, role=role)
    total = await service.count_users(db, search=search, role=role)
    return {"items": items, "total": total}


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    return await service.create(db, data)


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> User:
    user = await service.get_by_id(db, user_id)
    if user is None:
        raise UserNotFound()
    return user


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: uuid.UUID,
    data: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await service.get_by_id(db, user_id)
    if user is None:
        raise UserNotFound()
    return await service.update(db, user, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Soft-delete. The phone number stays reserved so the identity can't be
    re-registered by someone else."""
    user = await service.get_by_id(db, user_id)
    if user is None:
        raise UserNotFound()
    await service.soft_delete(db, user)
