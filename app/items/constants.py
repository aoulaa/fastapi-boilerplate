from enum import StrEnum


class ItemStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ErrorCode(StrEnum):
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    DUPLICATE_ITEM_NAME = "DUPLICATE_ITEM_NAME"
    ITEM_ARCHIVED = "ITEM_ARCHIVED"
