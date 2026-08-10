from fastapi import status

from app.auth.constants import ErrorCode
from app.exceptions import BadRequest, DetailedHTTPException, TooManyRequests


class InvalidToken(DetailedHTTPException):
    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = ErrorCode.INVALID_TOKEN


class InvalidOTP(BadRequest):
    DETAIL = ErrorCode.INVALID_OTP


class OTPExpired(BadRequest):
    DETAIL = ErrorCode.OTP_EXPIRED


class SMSSendFailed(DetailedHTTPException):
    STATUS_CODE = status.HTTP_503_SERVICE_UNAVAILABLE
    DETAIL = ErrorCode.SMS_SEND_FAILED


class SessionNotFound(DetailedHTTPException):
    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = ErrorCode.SESSION_NOT_FOUND


class SessionRevoked(DetailedHTTPException):
    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = ErrorCode.SESSION_REVOKED


class SessionExpired(DetailedHTTPException):
    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = ErrorCode.SESSION_EXPIRED


class TooManyOTPAttempts(TooManyRequests):
    DETAIL = ErrorCode.TOO_MANY_OTP_ATTEMPTS


class OTPSendCooldown(TooManyRequests):
    DETAIL = ErrorCode.OTP_SEND_COOLDOWN


class OTPSendRateLimited(TooManyRequests):
    """Per-IP or global daily OTP send budget exhausted."""

    DETAIL = ErrorCode.OTP_SEND_RATE_LIMITED


class InvalidCredentials(DetailedHTTPException):
    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = ErrorCode.INVALID_CREDENTIALS


class WrongOldPassword(BadRequest):
    DETAIL = ErrorCode.WRONG_OLD_PASSWORD


class LoginLocked(TooManyRequests):
    DETAIL = ErrorCode.LOGIN_LOCKED


class PasswordChangeLocked(TooManyRequests):
    DETAIL = ErrorCode.PASSWORD_CHANGE_LOCKED
