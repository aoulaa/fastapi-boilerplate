import uuid

from pydantic import Field

from app.items.constants import ItemStatus
from app.schemas import AwareDatetime, CustomModel, ORMModel


class ItemCreate(CustomModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: int = Field(default=0, ge=0)
    status: ItemStatus = ItemStatus.DRAFT


class ItemUpdate(CustomModel):
    """Every field optional — PATCH semantics. Unset fields are left alone
    (see `exclude_unset` in the service)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    status: ItemStatus | None = None


class ItemResponse(ORMModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    price: int
    status: ItemStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime | None
