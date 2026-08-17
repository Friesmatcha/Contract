from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr
    redis_url: SecretStr
    allowed_origins: list[str] = Field(default_factory=list)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_from: str | None = None
    frontend_base_url: str | None = None

    @field_validator("database_url", "redis_url")
    @classmethod
    def require_nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("database_url must use PostgreSQL with psycopg")
        return value

    @field_validator("redis_url")
    @classmethod
    def require_redis(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("redis_url must use Redis")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("wildcard origins are not allowed")
        return value

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_env not in {"local", "test"}


class SettingsConfigurationError(RuntimeError):
    def __init__(self, fields: tuple[str, ...]) -> None:
        self.fields = fields
        super().__init__(f"Invalid application configuration: {', '.join(fields)}")


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = tuple(sorted({str(error["loc"][0]) for error in exc.errors()}))
        raise SettingsConfigurationError(fields) from None
