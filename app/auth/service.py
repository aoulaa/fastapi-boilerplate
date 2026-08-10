"""Auth flows: OTP issue/verify, password login, session lifecycle.

Two login paths land on the same session machinery:

    send_otp → verify_otp ─┐
                           ├─→ create_session → (access JWT, raw refresh token)
    login_with_password ───┘

`rotate_session` swaps the refresh token on every use, so a stolen token is
usable at most once before the legitimate client's next refresh invalidates it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import auth_settings
from app.auth.constants import (
    LOGIN_FAIL_PREFIX,
    OTP_ATTEMPTS_PREFIX,
    OTP_COOLDOWN_PREFIX,
    OTP_GLOBAL_KEY,
    OTP_IP_PREFIX,
    OTP_PREFIX,
    PASSWORD_FAIL_PREFIX,
    SESSION_BLOCKLIST_PREFIX,
)
from app.auth.exceptions import (
    InvalidCredentials,
    InvalidOTP,
    LoginLocked,
    OTPExpired,
    OTPSendCooldown,
    OTPSendRateLimited,
    PasswordChangeLocked,
    SessionExpired,
    SessionNotFound,
    SessionRevoked,
    SMSSendFailed,
    TooManyOTPAttempts,
    WrongOldPassword,
)
from app.auth.models import Session
from app.auth.schemas import DeviceInfo, LoginRequest
from app.auth.utils import (
    generate_otp,
    generate_refresh_token,
    hash_password,
    hash_token,
    mask_phone,
    verify_password,
)
from app.config import settings
from app.constants import Environment
from app.eskiz import eskiz_client, record_sms_failure
from app.i18n import _
from app.user import service as user_service
from app.user.exceptions import AccountDeactivated
from app.user.models import User

logger = logging.getLogger(__name__)

_DAY_SECONDS = 86400


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _today_key() -> str:
    return _utcnow().strftime("%Y%m%d")


# ─── OTP ──────────────────────────────────────────────────────────────────────


async def _check_send_budgets(redis: Redis, phone_number: str, ip: str | None) -> None:
    """Three independent limits, cheapest first.

    1. per-phone cooldown — stops one user spamming "resend"
    2. per-IP daily cap — stops one client cycling through phone numbers
    3. global daily cap — circuit breaker on total SMS spend

    Counters are incremented in `_consume_send_budgets` only after the SMS
    actually goes out, so a provider outage doesn't eat the user's budget.
    """
    if await redis.exists(f"{OTP_COOLDOWN_PREFIX}{phone_number}"):
        raise OTPSendCooldown()

    if ip:
        ip_used = int(await redis.get(f"{OTP_IP_PREFIX}{ip}:{_today_key()}") or 0)
        if ip_used >= auth_settings.OTP_IP_DAILY_LIMIT:
            logger.warning("OTP IP budget exhausted for %s", ip)
            raise OTPSendRateLimited()

    global_used = int(await redis.get(f"{OTP_GLOBAL_KEY}:{_today_key()}") or 0)
    if global_used >= auth_settings.OTP_GLOBAL_DAILY_LIMIT:
        logger.error("OTP global daily budget exhausted (%d)", global_used)
        raise OTPSendRateLimited()


async def _consume_send_budgets(redis: Redis, phone_number: str, ip: str | None) -> None:
    day = _today_key()
    pipe = redis.pipeline()
    pipe.set(f"{OTP_COOLDOWN_PREFIX}{phone_number}", "1", ex=auth_settings.OTP_SEND_COOLDOWN)
    if ip:
        ip_key = f"{OTP_IP_PREFIX}{ip}:{day}"
        pipe.incr(ip_key)
        pipe.expire(ip_key, _DAY_SECONDS)
    global_key = f"{OTP_GLOBAL_KEY}:{day}"
    pipe.incr(global_key)
    pipe.expire(global_key, _DAY_SECONDS)
    await pipe.execute()


async def send_otp(phone_number: str, redis: Redis, *, ip: str | None = None) -> None:
    """Generate a code, store it in Redis, and SMS it.

    The code lives only in Redis with a TTL — nothing to clean up, and an
    expired code is indistinguishable from one that never existed.
    """
    await _check_send_budgets(redis, phone_number, ip)

    code = generate_otp()
    await redis.set(f"{OTP_PREFIX}{phone_number}", code, ex=auth_settings.OTP_EXP)
    await redis.delete(f"{OTP_ATTEMPTS_PREFIX}{phone_number}")

    text = _("Your verification code: {code}").format(code=code)
    try:
        await eskiz_client.send(phone_number.lstrip("+"), text)
    except Exception as exc:
        record_sms_failure(exc, context={"flow": "otp", "phone": mask_phone(phone_number)})
        # Drop the code: leaving it live would let a later attacker with the
        # same phone guess against a code the real user never received.
        await redis.delete(f"{OTP_PREFIX}{phone_number}")
        raise SMSSendFailed()

    await _consume_send_budgets(redis, phone_number, ip)

    if auth_settings.OTP_DEBUG_LOG and settings.ENVIRONMENT == Environment.LOCAL:
        logger.info("OTP for %s: %s", mask_phone(phone_number), code)


async def verify_otp(phone_number: str, code: str, redis: Redis) -> None:
    """Consume the code. Raises on expiry, mismatch, or too many attempts.

    A correct code is deleted immediately so it can't be replayed.
    """
    key = f"{OTP_PREFIX}{phone_number}"
    stored = await redis.get(key)
    if stored is None:
        raise OTPExpired()

    attempts_key = f"{OTP_ATTEMPTS_PREFIX}{phone_number}"
    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, auth_settings.OTP_EXP)
    if attempts > auth_settings.OTP_MAX_ATTEMPTS:
        # Burn the code — brute force past the limit must not be salvageable by
        # waiting for the attempt counter to lapse.
        await redis.delete(key, attempts_key)
        raise TooManyOTPAttempts()

    if str(stored) != code:
        raise InvalidOTP()

    await redis.delete(key, attempts_key)


# ─── Password login ───────────────────────────────────────────────────────────


async def login_with_password(db: AsyncSession, redis: Redis, data: LoginRequest) -> User:
    fail_key = f"{LOGIN_FAIL_PREFIX}{data.phone_number}"
    if int(await redis.get(fail_key) or 0) >= auth_settings.LOGIN_FAIL_LIMIT:
        raise LoginLocked()

    user = await user_service.get_by_phone(db, data.phone_number)
    # Same error for "no such user", "OTP-only account" and "wrong password" —
    # otherwise the endpoint is a phone-number enumeration oracle.
    if user is None or not user.password_hash or not verify_password(data.password, user.password_hash):
        attempts = await redis.incr(fail_key)
        if attempts == 1:
            await redis.expire(fail_key, auth_settings.LOGIN_LOCK_TTL)
        raise InvalidCredentials()

    if not user.is_active:
        raise AccountDeactivated()

    await redis.delete(fail_key)
    return user


async def change_password(
    db: AsyncSession,
    redis: Redis,
    user: User,
    old_password: str | None,
    new_password: str,
) -> None:
    """Set or replace the password. `old_password` is required once one exists."""
    if user.password_hash:
        fail_key = f"{PASSWORD_FAIL_PREFIX}{user.id}"
        if int(await redis.get(fail_key) or 0) >= auth_settings.PASSWORD_FAIL_LIMIT:
            raise PasswordChangeLocked()
        if not old_password or not verify_password(old_password, user.password_hash):
            attempts = await redis.incr(fail_key)
            if attempts == 1:
                await redis.expire(fail_key, auth_settings.PASSWORD_LOCK_TTL)
            raise WrongOldPassword()
        await redis.delete(fail_key)

    await user_service.set_password_hash(db, user, hash_password(new_password))


# ─── Sessions ─────────────────────────────────────────────────────────────────


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    device: DeviceInfo,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[Session, str]:
    """Create a session row. Returns `(session, raw_refresh_token)`.

    The raw token is returned exactly once — only its hash is persisted.
    """
    raw_refresh = generate_refresh_token()
    now = _utcnow()
    session = Session(
        user_id=user_id,
        refresh_token_hash=hash_token(raw_refresh),
        device_name=device.device_name,
        platform=device.platform.value if device.platform else None,
        app_version=device.app_version,
        ip_address=ip_address,
        user_agent=user_agent[:256] if user_agent else None,
        last_seen_at=now,
        expires_at=now + auth_settings.REFRESH_TOKEN_EXP,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, raw_refresh


async def rotate_session(
    db: AsyncSession,
    raw_refresh_token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[Session, str]:
    """Exchange a refresh token for a fresh one on the same session row.

    Rotation on every refresh means a leaked token has a short useful life: the
    moment either party refreshes, the other's copy stops working.
    """
    token_hash = hash_token(raw_refresh_token)
    result = await db.execute(select(Session).where(Session.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFound()
    if session.revoked_at is not None:
        raise SessionRevoked()
    if session.expires_at <= _utcnow():
        raise SessionExpired()

    new_raw = generate_refresh_token()
    session.refresh_token_hash = hash_token(new_raw)
    session.last_seen_at = _utcnow()
    if ip_address:
        session.ip_address = ip_address
    if user_agent:
        session.user_agent = user_agent[:256]
    await db.commit()
    await db.refresh(session)
    return session, new_raw


async def revoke_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID, redis: Redis) -> None:
    """Revoke one session and blocklist its still-valid access tokens.

    The blocklist entry only needs to outlive the longest possible access token,
    hence the JWT_EXP-derived TTL (+60s clock-skew margin).
    """
    result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id == user_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFound()
    if session.revoked_at is None:
        session.revoked_at = _utcnow()
        await db.commit()
    await redis.set(
        f"{SESSION_BLOCKLIST_PREFIX}{session_id}",
        "1",
        ex=auth_settings.JWT_EXP * 60 + 60,
    )


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID, redis: Redis) -> int:
    """Log the user out everywhere. Returns the number of sessions revoked."""
    result = await db.execute(select(Session.id).where(Session.user_id == user_id, Session.revoked_at.is_(None)))
    ids = list(result.scalars().all())
    if not ids:
        return 0
    await db.execute(update(Session).where(Session.id.in_(ids)).values(revoked_at=_utcnow()))
    await db.commit()
    pipe = redis.pipeline()
    for sid in ids:
        pipe.set(f"{SESSION_BLOCKLIST_PREFIX}{sid}", "1", ex=auth_settings.JWT_EXP * 60 + 60)
    await pipe.execute()
    return len(ids)


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None), Session.expires_at > _utcnow())
        .order_by(Session.last_seen_at.desc())
    )
    return result.scalars().all()


async def purge_dead_sessions(db: AsyncSession, *, older_than_days: int = 30) -> int:
    """Delete expired/revoked rows. Called from the worker cron."""
    cutoff = _utcnow() - timedelta(days=older_than_days)
    result = await db.execute(
        select(Session.id).where(
            (Session.expires_at < cutoff) | ((Session.revoked_at.is_not(None)) & (Session.revoked_at < cutoff))
        )
    )
    ids = list(result.scalars().all())
    if not ids:
        return 0
    for sid in ids:
        obj = await db.get(Session, sid)
        if obj is not None:
            await db.delete(obj)
    await db.commit()
    return len(ids)
