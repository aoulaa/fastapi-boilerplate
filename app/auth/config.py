import os
from datetime import timedelta

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".env")


class AuthConfig(BaseSettings):
    JWT_ALG: str = "HS256"
    JWT_SECRET: SecretStr
    # Short-lived on purpose: access tokens are stateless, so the only cheap
    # revocation is expiry. Instant revocation is handled by the Redis session
    # blocklist (see `constants.SESSION_BLOCKLIST_PREFIX`).
    JWT_EXP: int = 15  # minutes

    OTP_EXP: int = 300  # seconds
    OTP_LENGTH: int = 6
    OTP_MAX_ATTEMPTS: int = 5
    OTP_SEND_COOLDOWN: int = 60  # seconds between sends to the same phone

    # When True (and ENVIRONMENT=local), send_otp logs the plaintext code with a
    # masked phone. Off by default so codes never land in logs by accident.
    OTP_DEBUG_LOG: bool = False

    REFRESH_TOKEN_EXP: timedelta = timedelta(days=365)
    REFRESH_TOKEN_BYTES: int = 32  # urandom bytes → 64-char hex string

    SECURE_COOKIES: bool = True

    # Password login: per-phone failed-attempt lockout (Redis-backed).
    LOGIN_FAIL_LIMIT: int = 5
    LOGIN_LOCK_TTL: int = 900  # seconds — also the counter window

    # OTP send budgets layered on top of the per-phone cooldown. The IP cap
    # stops one client cycling phone numbers; the global budget is a circuit
    # breaker on the whole SMS spend.
    OTP_IP_DAILY_LIMIT: int = 20
    OTP_GLOBAL_DAILY_LIMIT: int = 2000

    # change_password: per-user failed old-password lockout, so a stolen access
    # token can't brute-force the current password.
    PASSWORD_FAIL_LIMIT: int = 5
    PASSWORD_LOCK_TTL: int = 900

    # Local-only superuser bootstrap (scripts/create_superuser.py). The script
    # aborts unless ENVIRONMENT=local.
    SUPERUSER_PHONE: str = "+998900000000"
    SUPERUSER_PASSWORD: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


auth_settings = AuthConfig()  # type: ignore[call-arg]
