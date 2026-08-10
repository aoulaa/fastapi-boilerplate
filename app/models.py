import importlib
import pkgutil
from datetime import datetime

from sqlalchemy import Boolean, DateTime, event, func
from sqlalchemy.orm import DeclarativeBase, Mapped, ORMExecuteState, Session, mapped_column, with_loader_criteria

from app.database import metadata


class Base(DeclarativeBase):
    metadata = metadata

    # `TimestampMixin.updated_at` has a SQL-expression `onupdate`, so its value is
    # computed by the DB. Under the default `eager_defaults="auto"` SQLAlchemy uses
    # RETURNING for INSERT but *not* UPDATE, leaving `updated_at` expired after an
    # UPDATE flush — the next attribute access emits a lazy SELECT. In a response
    # model that read happens in Pydantic's sync serializer, outside the greenlet
    # context, and raises MissingGreenlet. `True` puts RETURNING on the UPDATE too:
    # value fetched inline, no expiry, no extra query.
    __mapper_args__ = {"eager_defaults": True}


def import_all_models() -> None:
    """Import every `app/**/models.py` so all mappers are registered.

    Alembic autogenerate and the worker only import a subset of modules
    directly; without this, relationships to unimported models fail to resolve
    and migrations silently miss tables.
    """
    import app

    for _, name, _ in pkgutil.walk_packages(app.__path__, "app."):
        if name.endswith(".models"):
            importlib.import_module(name)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class SoftDeleteMixin:
    """Internal soft-delete tombstone. Never expose `is_deleted` in response schemas.

    Filtered out automatically by the `_apply_soft_delete_filter` session event
    below. To query deleted rows explicitly:
    ``query.execution_options(include_deleted=True)``.
    """

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


@event.listens_for(Session, "do_orm_execute")
def _apply_soft_delete_filter(execute_state: ORMExecuteState) -> None:
    if execute_state.is_select and not execute_state.execution_options.get("include_deleted", False):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(SoftDeleteMixin, lambda cls: cls.is_deleted.is_(False), include_aliases=True)
        )
