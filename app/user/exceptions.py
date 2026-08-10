from fastapi import status

from app.exceptions import BadRequest, DetailedHTTPException, NotFound, PermissionDenied
from app.user.constants import ErrorCode


class UserNotFound(NotFound):
    DETAIL = ErrorCode.USER_NOT_FOUND


class AccountDeactivated(DetailedHTTPException):
    STATUS_CODE = status.HTTP_403_FORBIDDEN
    DETAIL = ErrorCode.ACCOUNT_DEACTIVATED


class DuplicatePhone(BadRequest):
    DETAIL = ErrorCode.DUPLICATE_PHONE


class InsufficientRole(PermissionDenied):
    DETAIL = ErrorCode.INSUFFICIENT_ROLE
