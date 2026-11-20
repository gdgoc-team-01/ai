from pathlib import Path

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr | None = None
    max_image_bytes: PositiveInt | None = None
    allowed_image_formats: frozenset[str] | None = None

