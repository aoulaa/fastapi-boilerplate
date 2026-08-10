import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".env")


class EskizConfig(BaseSettings):
    # Blank email/password puts the client in stub mode: sends are logged and
    # return `{"status": "stubbed"}` instead of hitting the gateway. That's the
    # default for local dev and CI so nobody burns SMS credits by accident.
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: SecretStr = SecretStr("")
    ESKIZ_FROM: str = "4546"
    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.ESKIZ_EMAIL and self.ESKIZ_PASSWORD.get_secret_value())


eskiz_settings = EskizConfig()
