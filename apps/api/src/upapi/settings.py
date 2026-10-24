"""Ilova sozlamalari (03-arxitektura.md §10, §14).

Qiymatlar muhit o'zgaruvchilaridan (``UP_`` prefiksi) yoki ``.env`` dan; sirlar kodda va repozitoriyda yo'q.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UP_", env_file=".env", extra="ignore")

    env: Environment = Environment.DEV
    log_level: str = "INFO"
    # None — muhitga qarab: dev'da odam o'qiydigan, boshqalarida JSON (structlog).
    log_json: bool | None = None
    database_url: str = "postgresql://uzum:uzum@localhost:5432/uzum"

    @property
    def json_logs(self) -> bool:
        return self.log_json if self.log_json is not None else self.env is not Environment.DEV

    @property
    def show_error_details(self) -> bool:
        """500 xatolarida ichki tafsilot faqat dev/test'da ko'rinadi."""
        return self.env in (Environment.DEV, Environment.TEST)


@lru_cache
def get_settings() -> Settings:
    return Settings()
