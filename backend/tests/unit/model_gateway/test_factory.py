from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.integrations.model.deepseek import DeepSeekModelGateway
from backend.app.integrations.model.factory import create_model_gateway
from backend.app.integrations.model.gateway import ModelConfigurationError
from backend.app.integrations.model.qwen import QwenModelGateway


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": SecretStr("postgresql+psycopg://user:secret@db/contract"),
        "redis_url": SecretStr("redis://:secret@redis:6379/0"),
        "model_api_key": SecretStr("provider-secret-placeholder"),
        "model_name": "deepseek-v4-flash",
    }
    values.update(overrides)
    return Settings(**values)


def test_factory_selects_deepseek_and_uses_deepseek_defaults() -> None:
    gateway = create_model_gateway(_settings(model_provider="deepseek"))

    assert isinstance(gateway, DeepSeekModelGateway)
    assert gateway.provider == "deepseek"
    assert gateway.endpoint == "https://api.deepseek.com/chat/completions"
    assert gateway.max_tokens == 2048


def test_factory_selects_qwen_without_using_deepseek_default_endpoint() -> None:
    gateway = create_model_gateway(
        _settings(
            model_provider="qwen",
            model_name="qwen-test-model",
            model_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
    )

    assert isinstance(gateway, QwenModelGateway)
    assert gateway.provider == "qwen"
    assert gateway.endpoint.endswith("/compatible-mode/v1/chat/completions")


def test_factory_rejects_unknown_provider_without_fallback() -> None:
    settings = _settings()

    try:
        create_model_gateway(settings, provider_override="unsupported")
    except ModelConfigurationError as error:
        assert error.code == "MODEL_UNKNOWN_PROVIDER"
    else:
        raise AssertionError("unknown provider must fail")
