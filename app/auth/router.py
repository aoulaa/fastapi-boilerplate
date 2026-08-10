import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.config import auth_settings
from app.auth.dependencies import get_current_active_user, get_current_session_id
from app.auth.exceptions import SessionNotFound
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    OTPVerifyRequest,
    PhoneRequest,
    RefreshRequest,
    SessionResponse,
    TokenPairResponse,
)
from app.auth.utils import create_access_token
from app.database import get_db
from app.redis import get_redis
from app.user import service as user_service
from app.user.exceptions import AccountDeactivated
from app.user.models import User

router = APIRouter()


def _token_pair(user: User, session_id: uuid.UUID, raw_refresh: str) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=create_access_token(str(user.id), str(session_id), role=user.role.value),
        refresh_token=raw_refresh,
        expires_in=auth_settings.JWT_EXP * 60,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/send-otp", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def send_otp(
    data: PhoneRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
) -> None:
    """Always 204 on success — the response must not reveal whether the number
    is registered."""
    await service.send_otp(data.phone_number, redis, ip=_client_ip(request))


@router.post("/verify-otp", response_model=TokenPairResponse)
async def verify_otp(
    data: OTPVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    """Verify the code and log in. First successful verification registers the account."""
    await service.verify_otp(data.phone_number, data.code, redis)
    user = await user_service.get_or_create_by_phone(db, data.phone_number)
    if not user.is_active:
        raise AccountDeactivated()
    session, raw_refresh = await service.create_session(
        db,
        user.id,
        data,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _token_pair(user, session.id, raw_refresh)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    user = await service.login_with_password(db, redis, data)
    session, raw_refresh = await service.create_session(
        db,
        user.id,
        data,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _token_pair(user, session.id, raw_refresh)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    data: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    session, raw_refresh = await service.rotate_session(
        db,
        data.refresh_token,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # Re-read the user so a role change or a deactivation takes effect at the
    # refresh boundary rather than whenever the client happens to log in again.
    user = await user_service.get_by_id(db, session.user_id)
    if user is None:
        raise SessionNotFound()
    if not user.is_active:
        raise AccountDeactivated()
    return _token_pair(user, session.id, raw_refresh)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_active_user),
) -> None:
    await service.change_password(db, redis, user, data.old_password, data.new_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_active_user),
    session_id: uuid.UUID | None = Depends(get_current_session_id),
) -> None:
    if session_id:
        await service.revoke_session(db, session_id, user.id, redis)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list:
    return list(await service.list_sessions(db, user.id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_active_user),
) -> None:
    await service.revoke_session(db, session_id, user.id, redis)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_all_sessions(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_active_user),
) -> None:
    """Log out of every device, including this one."""
    await service.revoke_all_sessions(db, user.id, redis)
