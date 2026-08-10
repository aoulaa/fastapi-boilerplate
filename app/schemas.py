from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, PlainSerializer


def _fmt_dt(v: datetime) -> str:
    """Always serialize datetimes with an explicit offset.

    Naive values are assumed UTC — the DB stores `timestamptz`, so anything
    naive got there through a code path that dropped the tzinfo.
    """
    if v.tzinfo is None:
        v = v.replace(tzinfo=ZoneInfo("UTC"))
    return v.strftime("%Y-%m-%dT%H:%M:%S%z")


AwareDatetime = Annotated[datetime, PlainSerializer(_fmt_dt, return_type=str, when_used="json")]

T = TypeVar("T")


class CustomModel(BaseModel):
    """Base for every request/response schema."""

    model_config = ConfigDict(populate_by_name=True)

    def serializable_dict(self, **kwargs: Any) -> dict[str, Any]:
        """JSON-safe dict (UUIDs → str, datetimes → str), for Redis/queue payloads."""
        return dict(jsonable_encoder(self.model_dump(**kwargs)))


class ORMModel(CustomModel):
    """Response schema that reads straight off a SQLAlchemy row."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PaginatedResponse(CustomModel, Generic[T]):
    """`{"items": [...], "total": n}` — the one list envelope used everywhere.

    `total` is the unpaginated count so clients can render page controls.
    """

    items: list[T]
    total: int
