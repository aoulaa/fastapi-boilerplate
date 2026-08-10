from enum import StrEnum


class Role(StrEnum):
    """Ordered least → most privileged. See `ROLE_RANK` for comparisons."""

    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"


# Numeric rank so `require_role` can express "this role or above" without a
# chain of ifs. Add a role here the moment you add it to the enum.
ROLE_RANK: dict[Role, int] = {
    Role.USER: 0,
    Role.MANAGER: 10,
    Role.ADMIN: 20,
}


class ErrorCode(StrEnum):
    USER_NOT_FOUND = "USER_NOT_FOUND"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"
    DUPLICATE_PHONE = "DUPLICATE_PHONE"
    INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"
