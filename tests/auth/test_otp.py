import pytest
from redis.asyncio import Redis

from app.auth import service
from app.auth.config import auth_settings
from app.auth.constants import OTP_PREFIX
from app.auth.exceptions import InvalidOTP, OTPExpired, OTPSendCooldown, TooManyOTPAttempts

PHONE = "+998901234567"


async def _issue(redis: Redis) -> str:
    await service.send_otp(PHONE, redis, ip="1.2.3.4")
    code = await redis.get(f"{OTP_PREFIX}{PHONE}")
    assert code is not None
    return str(code)


async def test_send_and_verify(redis: Redis) -> None:
    code = await _issue(redis)
    await service.verify_otp(PHONE, code, redis)
    # Consumed: a correct code must not be replayable.
    assert await redis.get(f"{OTP_PREFIX}{PHONE}") is None


async def test_verify_without_send_is_expired(redis: Redis) -> None:
    with pytest.raises(OTPExpired):
        await service.verify_otp(PHONE, "000000", redis)


async def test_wrong_code_rejected(redis: Redis) -> None:
    code = await _issue(redis)
    wrong = "1" * len(code) if code != "1" * len(code) else "2" * len(code)
    with pytest.raises(InvalidOTP):
        await service.verify_otp(PHONE, wrong, redis)


async def test_attempt_limit_burns_the_code(redis: Redis) -> None:
    code = await _issue(redis)
    wrong = "1" * len(code) if code != "1" * len(code) else "2" * len(code)
    for _ in range(auth_settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(InvalidOTP):
            await service.verify_otp(PHONE, wrong, redis)
    with pytest.raises(TooManyOTPAttempts):
        await service.verify_otp(PHONE, wrong, redis)
    # Even the *correct* code is dead now — waiting out the attempt counter
    # must not resurrect a brute-forced code.
    with pytest.raises(OTPExpired):
        await service.verify_otp(PHONE, code, redis)


async def test_resend_is_rate_limited(redis: Redis) -> None:
    await _issue(redis)
    with pytest.raises(OTPSendCooldown):
        await service.send_otp(PHONE, redis, ip="1.2.3.4")
