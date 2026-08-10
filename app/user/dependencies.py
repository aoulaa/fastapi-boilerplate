"""Role gates and generic ownership lookup.

Import `get_current_active_user` from `app.auth.dependencies`; this module adds
the authorisation layer on top of it.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.exceptions import NotFound
from app.user.constants import ROLE_RANK, Role
from app.user.exceptions import InsufficientRole
from app.user.models import User

T = TypeVar("T")


def require_role(minimum: Role) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: caller must hold `minimum` or a higher-ranked role.

        @router.delete("", dependencies=[Depends(require_role(Role.ADMIN))])

    Rank comparison (not equality) so adding a role above ADMIN later doesn't
    silently lock existing admin-only endpoints.
    """

    async def _check(user: User = Depends(get_current_active_user)) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise InsufficientRole()
        return user

    return _check


require_manager = require_role(Role.MANAGER)
require_admin = require_role(Role.ADMIN)


def owned_resource(
    getter: Callable[[AsyncSession, uuid.UUID], Awaitable[Any]],
    *,
    not_found: type[NotFound] = NotFound,
    owner_field: str = "owner_id",
) -> Callable[..., Awaitable[Any]]:
    """Dependency factory: fetch `{resource_id}` and assert the caller owns it.

    Returns 404 (not 403) when another user's row is requested, so the endpoint
    doesn't leak which IDs exist. Admins bypass the ownership check.

        valid_item = owned_resource(service.get_by_id, not_found=ItemNotFound)

    The route must declare the path param as `{resource_id}`.
    """

    async def _dependency(
        resource_id: uuid.UUID = Path(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_active_user),
    ) -> Any:
        obj = await getter(db, resource_id)
        if obj is None:
            raise not_found()
        if user.role != Role.ADMIN and getattr(obj, owner_field, None) != user.id:
            raise not_found()
        return obj

    return _dependency
