import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class Session(Base, TimestampMixin):
    """One row per logged-in device. Holds the *hash* of the refresh token.

    Access tokens are stateless and short-lived; the refresh token is the real
    credential, so only its SHA-256 lands in the DB — a database leak can't be
    replayed against the API. Revocation is immediate for access tokens too,
    via the Redis blocklist keyed on this row's id (the JWT `sid` claim).
    """

    __tablename__ = "session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    device_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # 45 = max IPv6 text length
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Supports the "purge dead sessions" sweep without a full table scan.
    __table_args__ = (Index("session_expires_revoked_idx", "expires_at", "revoked_at"),)
