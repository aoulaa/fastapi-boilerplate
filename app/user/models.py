import uuid

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import Language
from app.models import Base, SoftDeleteMixin, TimestampMixin
from app.user.constants import Role


class User(Base, TimestampMixin, SoftDeleteMixin):
    """An account. Identified by phone number — the OTP login is the primary path.

    `password_hash` is nullable: an OTP-only account never sets a password, and
    the password login path treats "no hash" as "this user cannot log in with a
    password" rather than "any password works".
    """

    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # E.164, e.g. +998901234567. Unique across soft-deleted rows too — the
    # number is the login identity, so recycling it would hand over the old
    # account. `service.create` maps the IntegrityError to DUPLICATE_PHONE.
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)

    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Role.USER,
        server_default=Role.USER.value,
    )
    language: Mapped[Language] = mapped_column(
        Enum(Language, name="language", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Language.EN,
        server_default=Language.EN.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
