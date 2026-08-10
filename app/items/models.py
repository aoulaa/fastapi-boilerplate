import uuid

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.items.constants import ItemStatus
from app.models import Base, SoftDeleteMixin, TimestampMixin
from app.user.models import User


class Item(Base, TimestampMixin, SoftDeleteMixin):
    """Example domain model — copy this file when starting a new module.

    Shows the four things almost every table here needs: a UUID PK, an owner FK
    for the ownership check, the timestamp/soft-delete mixins, and DB-level
    constraints that don't rely on the application being correct.
    """

    __tablename__ = "item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Money as an integer in the smallest currency unit. Never float — 0.1 + 0.2
    # is not 0.3, and that eventually shows up on an invoice.
    price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")

    status: Mapped[ItemStatus] = mapped_column(
        Enum(ItemStatus, name="item_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ItemStatus.DRAFT,
        server_default=ItemStatus.DRAFT.value,
    )

    owner: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        # Names are unique per owner, not globally — two users may each have an
        # "Invoice template". Soft-deleted rows still occupy the name; that's
        # intentional so an undelete can't collide.
        UniqueConstraint("owner_id", "name", name="item_owner_name_key"),
        # Alembic autogenerate cannot see CHECK constraints, so this one is
        # covered by a test instead of by migration drift detection.
        CheckConstraint("price >= 0", name="price_non_negative"),
    )
