import uuid

from pydantic import Field, field_validator

from app.auth.constants import Platform
from app.schemas import AwareDatetime, CustomModel, ORMModel
from app.user.schemas import PHONE_PATTERN

DEVICE_NAME_MAX_LENGTH = 128


def _truncate_device_name(v: str | None) -> str | None:
    """Clamp `device_name` to the column width instead of rejecting.

    `device_name` is best-effort telemetry (clients send the browser
    User-Agent). Long Safari/Yandex UA strings run past 128 chars, and a hard
    `max_length` would 422 the entire login — surfacing as a generic "check your
    fields" error the user can neither see nor fix. Truncate instead, so a
    cosmetic field never blocks auth. Used as a `mode="before"` validator.
    """
    if isinstance(v, str) and len(v) > DEVICE_NAME_MAX_LENGTH:
        return v[:DEVICE_NAME_MAX_LENGTH]
    return v


class DeviceInfo(CustomModel):
    """Optional client metadata recorded on the session row."""

    device_name: str | None = Field(default=None, max_length=DEVICE_NAME_MAX_LENGTH)
    platform: Platform | None = None
    app_version: str | None = Field(default=None, max_length=32)

    @field_validator("device_name", mode="before")
    @classmethod
    def _clamp_device_name(cls, v: str | None) -> str | None:
        return _truncate_device_name(v)


class PhoneRequest(CustomModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)


class OTPVerifyRequest(DeviceInfo):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    code: str = Field(min_length=4, max_length=8)


class LoginRequest(DeviceInfo):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    password: str


class TokenPairResponse(CustomModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expires


class RefreshRequest(CustomModel):
    refresh_token: str


class SessionResponse(ORMModel):
    id: uuid.UUID
    device_name: str | None
    platform: str | None
    app_version: str | None
    ip_address: str | None
    created_at: AwareDatetime
    last_seen_at: AwareDatetime
    expires_at: AwareDatetime


def validate_password(v: str) -> str:
    """Policy: 8-128 chars, at least one letter and one digit, no control chars."""
    if not (8 <= len(v) <= 128):
        raise ValueError("password length must be 8-128 characters")
    if not any(c.isalpha() for c in v):
        raise ValueError("password must contain at least one letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("password must contain at least one digit")
    if any(ord(c) < 32 or ord(c) == 127 for c in v):
        raise ValueError("password must not contain control characters")
    return v


class ChangePasswordRequest(CustomModel):
    # Optional only when the caller has no password set yet — enforced in the
    # service, which knows whether a hash exists.
    old_password: str | None = None
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password(v)
