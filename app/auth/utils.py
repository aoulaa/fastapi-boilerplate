import base64
import hashlib
import hmac
import os
import secrets
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import jwt

from app.auth.config import auth_settings

# scrypt parameters tuned for ~50ms per hash on modern hardware. They're baked
# into the encoded string, so changing them here needs a rehash-on-login path.
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16


def generate_otp() -> str:
    """`secrets`, not `random` — the code is a credential."""
    return "".join(secrets.choice(string.digits) for _ in range(auth_settings.OTP_LENGTH))


def create_access_token(user_id: str, session_id: str, *, role: str) -> str:
    """Mint a short-lived access token.

    `role` is embedded so trivial gates don't need a DB round-trip, but it goes
    stale on a role change until the token expires — anything destructive should
    re-read the user row (as every `require_role` dependency here does).
    """
    payload = {
        "id": user_id,
        "sid": session_id,
        "role": role,
        "exp": datetime.now(ZoneInfo("UTC")) + timedelta(minutes=auth_settings.JWT_EXP),
    }
    return jwt.encode(payload, auth_settings.JWT_SECRET.get_secret_value(), algorithm=auth_settings.JWT_ALG)


def generate_refresh_token() -> str:
    """Cryptographically random hex string. Returned to the client once, never stored raw."""
    return os.urandom(auth_settings.REFRESH_TOKEN_BYTES).hex()


def hash_token(token: str) -> str:
    """SHA-256 hex digest — store this, never the raw token.

    Plain SHA-256 (not scrypt) is deliberate: the token is 256 bits of entropy,
    so there is nothing to brute-force, and this runs on every refresh.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def hash_password(plain: str) -> str:
    """Return the encoded scrypt hash. Format: ``scrypt$N$r$p$salt_b64$hash_b64``."""
    salt = os.urandom(_SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(digest)}"


def verify_password(plain: str, encoded: str) -> bool:
    """Constant-time verification. Malformed input returns False (never raises).

    Parameters are pinned to the canonical constants so a tampered hash row
    cannot force a weaker cost factor at verification time.
    """
    try:
        scheme, n_s, r_s, p_s, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        if (int(n_s), int(r_s), int(p_s)) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P):
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        if len(expected) != _SCRYPT_DKLEN:
            return False
    except (ValueError, AttributeError):
        return False
    try:
        computed = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
    except (ValueError, OverflowError):
        return False
    return hmac.compare_digest(computed, expected)


def mask_phone(phone: str) -> str:
    """`+998901234567` → `+998****4567`. For logs — never log the full number."""
    if len(phone) <= 8:
        return "*" * len(phone)
    return f"{phone[:4]}****{phone[-4:]}"
