from app.exceptions import BadRequest, Conflict, NotFound
from app.items.constants import ErrorCode


class ItemNotFound(NotFound):
    DETAIL = ErrorCode.ITEM_NOT_FOUND


class DuplicateItemName(Conflict):
    DETAIL = ErrorCode.DUPLICATE_ITEM_NAME


class ItemArchived(BadRequest):
    DETAIL = ErrorCode.ITEM_ARCHIVED
