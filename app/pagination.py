from fastapi import Query
from pydantic import BaseModel


class PaginationParams(BaseModel):
    limit: int
    offset: int


async def pagination(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginationParams:
    """Shared `?limit=&offset=` dependency. Pair with `PaginatedResponse`."""
    return PaginationParams(limit=limit, offset=offset)
