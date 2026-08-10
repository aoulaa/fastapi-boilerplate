"""Global settings.

Split into one `BaseSettings` class per concern, then composed into a single
`Settings`. Module-local settings (auth, eskiz) live next to their module and
read the same `.env` — so a module can be lifted out of this repo without
dragging unrelated config with it.
"""

import os

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import Environment

_ENV_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".env")


class AppSettings(BaseSettings):
    APP_NAME: str = "FastAPI Boilerplate"
    APP_VERSION: str = "0.1.0"


class DatabaseSettings(BaseSettings):
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "app"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        creds = f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
        host = f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"postgresql+asyncpg://{creds}@{host}"


class RedisSettings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"


class CORSSettings(BaseSettings):
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    CORS_ORIGINS_REGEX: str | None = None
    CORS_HEADERS: list[str] = ["*"]


class EnvironmentSettings(BaseSettings):
    ENVIRONMENT: Environment = Environment.LOCAL
    SITE_DOMAIN: str = "example.com"


class SentrySettings(BaseSettings):
    SENTRY_DSN: str | None = None


class Settings(
    AppSettings,
    DatabaseSettings,
    RedisSettings,
    CORSSettings,
    EnvironmentSettings,
    SentrySettings,
):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
