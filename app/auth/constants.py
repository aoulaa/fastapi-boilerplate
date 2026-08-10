from enum import StrEnum

# Redis key prefixes. Kept here (not inlined) so a `KEYS`-style audit or a
# migration to a namespaced Redis DB has one place to look.
SESSION_BLOCKLIST_PREFIX = "session:revoked:"
OTP_PREFIX = "otp:code:"
OTP_ATTEMPTS_PREFIX = "otp:attempts:"
OTP_COOLDOWN_PREFIX = "otp:cooldown:"
OTP_IP_PREFIX = "otp:ip:"
OTP_GLOBAL_KEY = "otp:global"
LOGIN_FAIL_PREFIX = "login:fail:"
PASSWORD_FAIL_PREFIX = "password:fail:"


class Platform(StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class ErrorCode(StrEnum):
    INVALID_TOKEN = "INVALID_TOKEN"
    INVALID_OTP = "INVALID_OTP"
    OTP_EXPIRED = "OTP_EXPIRED"
    SMS_SEND_FAILED = "SMS_SEND_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_REVOKED = "SESSION_REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TOO_MANY_OTP_ATTEMPTS = "TOO_MANY_OTP_ATTEMPTS"
    OTP_SEND_COOLDOWN = "OTP_SEND_COOLDOWN"
    OTP_SEND_RATE_LIMITED = "OTP_SEND_RATE_LIMITED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    WRONG_OLD_PASSWORD = "WRONG_OLD_PASSWORD"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    PASSWORD_CHANGE_LOCKED = "PASSWORD_CHANGE_LOCKED"
