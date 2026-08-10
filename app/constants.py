from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_debug(self) -> bool:
        """Debug-only affordances: OpenAPI docs, query counter, verbose logs."""
        return self in (Environment.LOCAL, Environment.STAGING)


class Language(StrEnum):
    """Supported UI/notification languages. Must match the `locales/` dirs."""

    UZ = "uz"
    RU = "ru"
    EN = "en"
