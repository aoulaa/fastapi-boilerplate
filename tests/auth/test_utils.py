import jwt
import pytest

from app.auth.config import auth_settings
from app.auth.utils import (
    create_access_token,
    generate_otp,
    generate_refresh_token,
    hash_password,
    hash_token,
    mask_phone,
    verify_password,
)


def test_password_roundtrip() -> None:
    encoded = hash_password("hunter2000")
    assert verify_password("hunter2000", encoded)
    assert not verify_password("hunter2001", encoded)


def test_password_hash_is_salted() -> None:
    """Same password, different hash — otherwise the table is a rainbow-table target."""
    assert hash_password("hunter2000") != hash_password("hunter2000")


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "not-a-hash",
        "scrypt$1$1$1$aaaa$bbbb",  # weakened cost parameters must be rejected
        "bcrypt$16384$8$1$aaaa$bbbb",  # wrong scheme
    ],
)
def test_verify_password_rejects_malformed(encoded: str) -> None:
    assert verify_password("hunter2000", encoded) is False


def test_generate_otp_length_and_digits() -> None:
    code = generate_otp()
    assert len(code) == auth_settings.OTP_LENGTH
    assert code.isdigit()


def test_refresh_token_is_random_and_hashed() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()
    assert a != b
    assert len(a) == auth_settings.REFRESH_TOKEN_BYTES * 2
    assert hash_token(a) == hash_token(a) != hash_token(b)


def test_access_token_carries_claims() -> None:
    token = create_access_token("user-1", "session-1", role="admin")
    payload = jwt.decode(
        token,
        auth_settings.JWT_SECRET.get_secret_value(),
        algorithms=[auth_settings.JWT_ALG],
    )
    assert payload["id"] == "user-1"
    assert payload["sid"] == "session-1"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token("user-1", "session-1", role="user")
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, "wrong-secret", algorithms=[auth_settings.JWT_ALG])


def test_mask_phone() -> None:
    assert mask_phone("+998901234567") == "+998****4567"
    assert "1234" not in mask_phone("+1234")
