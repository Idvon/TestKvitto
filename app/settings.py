"""Application settings loaded from the environment / ``.env`` via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration.

    ``database_url`` is validated as a Postgres DSN and ``webhook_secret`` is
    the HMAC key used to verify bank webhook signatures. Both are read from the
    environment (or a local ``.env`` file); there is no static fallback.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn
    webhook_secret: str


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
