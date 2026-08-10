"""Base HTTP exceptions.

Every domain error subclasses one of these and sets `DETAIL` to an UPPERCASE
machine-readable code from its module's `ErrorCode` enum — never a prose
sentence. The client maps the code to a localized message, so the backend never
has to guess the caller's language.
"""

from typing import Any

from fastapi import HTTPException, status


class DetailedHTTPException(HTTPException):
    STATUS_CODE = status.HTTP_500_INTERNAL_SERVER_ERROR
    DETAIL = "SERVER_ERROR"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(status_code=self.STATUS_CODE, detail=self.DETAIL, **kwargs)


class PermissionDenied(DetailedHTTPException):
    STATUS_CODE = status.HTTP_403_FORBIDDEN
    DETAIL = "PERMISSION_DENIED"


class NotFound(DetailedHTTPException):
    STATUS_CODE = status.HTTP_404_NOT_FOUND
    DETAIL = "NOT_FOUND"


class BadRequest(DetailedHTTPException):
    STATUS_CODE = status.HTTP_400_BAD_REQUEST
    DETAIL = "BAD_REQUEST"


class Conflict(DetailedHTTPException):
    STATUS_CODE = status.HTTP_409_CONFLICT
    DETAIL = "CONFLICT"


class UnprocessableContent(DetailedHTTPException):
    STATUS_CODE = status.HTTP_422_UNPROCESSABLE_CONTENT
    DETAIL = "UNPROCESSABLE_CONTENT"


class TooManyRequests(DetailedHTTPException):
    STATUS_CODE = status.HTTP_429_TOO_MANY_REQUESTS
    DETAIL = "TOO_MANY_REQUESTS"
