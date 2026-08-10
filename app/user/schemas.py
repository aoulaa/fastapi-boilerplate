import uuid

from pydantic import Field

from app.constants import Language
from app.schemas import AwareDatetime, CustomModel, ORMModel
from app.user.constants import Role

PHONE_PATTERN = r"^\+\d{7,15}$"


class UserResponse(ORMModel):
    id: uuid.UUID
    phone_number: str
    full_name: str | None
    role: Role
    language: Language
    is_active: bool
    created_at: AwareDatetime


class UserUpdate(CustomModel):
    """Self-service profile edit. Role and is_active are deliberately absent —
    privilege changes go through the admin endpoint."""

    full_name: str | None = Field(default=None, max_length=128)
    language: Language | None = None


class UserAdminUpdate(CustomModel):
    """Admin-only mutation of another account."""

    full_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None


class UserCreate(CustomModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    full_name: str | None = Field(default=None, max_length=128)
    role: Role = Role.USER
