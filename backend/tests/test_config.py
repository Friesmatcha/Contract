import pytest
from pydantic import SecretStr

from backend.app.config import Settings, SettingsConfigurationError, get_settings


def test_settings_hide_connection_strings() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
        redis_url=SecretStr("redis://:secret@redis:6379/0"),
        model_api_key=SecretStr("deepseek-secret-placeholder"),
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


def test_model_base_url_is_loaded_as_non_secret_configuration() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
        redis_url=SecretStr("redis://:secret@redis:6379/0"),
        model_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    assert settings.model_base_url.endswith("/compatible-mode/v1")


def test_deepseek_is_the_default_model_configuration() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
        redis_url=SecretStr("redis://:secret@redis:6379/0"),
        model_api_key=SecretStr("deepseek-secret-placeholder"),
        _env_file=None,
    )

    assert settings.model_provider == "deepseek"
    assert settings.model_name == "deepseek-v4-flash"
    assert settings.model_base_url == "https://api.deepseek.com"
    assert settings.model_max_tokens == 2048
    assert settings.model_thinking_mode == "disabled"
    assert isinstance(settings.model_api_key, SecretStr)


def test_model_base_url_is_normalized_and_secure() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
        redis_url=SecretStr("redis://:secret@redis:6379/0"),
        model_base_url="https://api.deepseek.com///",
    )

    assert settings.model_base_url == "https://api.deepseek.com"

    for invalid in (
        "http://api.deepseek.com",
        "https://token:secret@api.deepseek.com",
        "https://api.deepseek.com?api_key=secret",
        "https://api.deepseek.com#fragment",
        "",
    ):
        with pytest.raises(ValueError):
            Settings(
                database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
                redis_url=SecretStr("redis://:secret@redis:6379/0"),
                model_base_url=invalid,
            )


@pytest.mark.parametrize("value", [0, -1, 384001])
def test_model_max_tokens_has_a_bounded_positive_range(value: int) -> None:
    with pytest.raises(ValueError):
        Settings(
            database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
            redis_url=SecretStr("redis://:secret@redis:6379/0"),
            model_max_tokens=value,
        )


def test_unknown_model_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(
            database_url=SecretStr("postgresql+psycopg://user:secret@db/contract"),
            redis_url=SecretStr("redis://:secret@redis:6379/0"),
            model_provider="unknown",
        )
