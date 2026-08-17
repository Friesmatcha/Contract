import pytest
from pydantic import SecretStr

from backend.app.config import Settings, SettingsConfigurationError, get_settings


def test_settings_hide_connection_strings() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
        redis_url=SecretStr("redis://:secret@redis:6379/0"),
    )

    rendered = repr(settings)

    assert "user:secret" not in rendered
    assert ":secret@redis" not in rendered


def test_missing_required_settings_report_only_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()

    with pytest.raises(SettingsConfigurationError) as exc_info:
        get_settings()

    assert exc_info.value.fields == ("database_url", "redis_url")
    assert "postgresql" not in str(exc_info.value)


def test_non_postgresql_database_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(
            database_url=SecretStr("sqlite:///contract.db"),
            redis_url=SecretStr("redis://localhost:6379/0"),
        )
