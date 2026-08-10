import uuid
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import auth_settings
from app.auth.constants import SESSION_BLOCKLIST_PREFIX
from app.auth.exceptions import InvalidToken
from app.database import get_db
from app.redis import get_redis
from app.user import service as user_service
from app.user.exceptions import AccountDeactivated, UserNotFound
from app.user.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def parse_jwt_data(
    token: str = Depends(oauth2_scheme),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Decode + validate the access token. Cheap: no DB hit, one Redis GET.

    Endpoints that only need the caller's id or role can depend on this
    directly and skip the user lookup entirely.
    """
    try:
        payload = jwt.decode(
            token,
            auth_settings.JWT_SECRET.get_secret_value(),
            algorithms=[auth_settings.JWT_ALG],
        )
    except InvalidTokenError:
        raise InvalidToken()

    sid = payload.get("sid")
    # Logout/revocation blocklist — without this, an access token stays valid
    # for up to JWT_EXP minutes after the user logs out.
    if sid and await redis.exists(f"{SESSION_BLOCKLIST_PREFIX}{sid}"):
        raise InvalidToken()

    user_id = payload.get("id")
    if user_id is None:
        raise InvalidToken()
    return {"user_id": user_id, "session_id": sid, "role": payload.get("role")}


async def get_current_user(
    token_data: dict[str, Any] = Depends(parse_jwt_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await user_service.get_by_id(db, uuid.UUID(token_data["user_id"]))
    if not user:
        raise UserNotFound()
    return user


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    """The default auth dependency. Use this unless you have a reason not to."""
    if not user.is_active:
        raise AccountDeactivated()
    return user


async def get_current_session_id(
    token_data: dict[str, Any] = Depends(parse_jwt_data),
) -> uuid.UUID | None:
    sid = token_data.get("session_id")
    return uuid.UUID(sid) if sid else None
