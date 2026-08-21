from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

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
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    model_provider: Literal["qwen", "deepseek"] = "deepseek"
    model_name: str | None = Field(default="deepseek-v4-flash", max_length=255)
    model_api_key: SecretStr | None = None
    model_base_url: str = "https://api.deepseek.com"
    model_max_tokens: int = Field(default=2048, ge=1, le=384_000)
    model_thinking_mode: Literal["disabled", "enabled"] = "disabled"
    file_storage_root: str = "/var/lib/contract-review/files"
    clamav_host: str = "clamav"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: float = Field(default=10, gt=0, le=60)

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

    @field_validator("model_name")
    @classmethod
    def normalize_optional_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("model_base_url")
    @classmethod
    def normalize_model_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            not normalized
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "model_base_url must be an HTTPS URL without credentials, query, or fragment"
            )
        return normalized

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
