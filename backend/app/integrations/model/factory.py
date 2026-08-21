"""Provider-neutral construction for Worker and evaluation callers."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.request import urlopen

from backend.app.config import Settings
from backend.app.integrations.model.deepseek import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DeepSeekModelGateway,
    deepseek_endpoint_from_base_url,
)
from backend.app.integrations.model.fake import FakeModelGateway
from backend.app.integrations.model.gateway import ModelConfigurationError, ModelGateway
from backend.app.integrations.model.qwen import (
    DEFAULT_QWEN_BASE_URL,
    QwenModelGateway,
    qwen_endpoint_from_base_url,
)

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_QWEN_MODEL = "qwen3.8-max"


def create_model_gateway(
    settings: Settings,
    *,
    provider_override: str | None = None,
    opener: Callable[..., Any] | None = None,
    max_retries: int | None = None,
    cost_per_1k_input: Decimal | None = None,
    cost_per_1k_output: Decimal | None = None,
) -> ModelGateway:
    provider = provider_override or settings.model_provider
    retries = 3 if max_retries is None else max_retries
    endpoint_base = settings.model_base_url
    model = settings.model_name
    if provider == "qwen":
        if endpoint_base == DEFAULT_DEEPSEEK_BASE_URL:
            endpoint_base = DEFAULT_QWEN_BASE_URL
        if model is None or model == DEFAULT_DEEPSEEK_MODEL:
            model = DEFAULT_QWEN_MODEL
        return QwenModelGateway(
            api_key=settings.model_api_key,
            model=model,
            endpoint=qwen_endpoint_from_base_url(endpoint_base),
            max_retries=retries,
            opener=opener or urlopen,
            cost_per_1k_input=cost_per_1k_input,
            cost_per_1k_output=cost_per_1k_output,
        )
    if provider == "deepseek":
        if endpoint_base == DEFAULT_QWEN_BASE_URL:
            endpoint_base = DEFAULT_DEEPSEEK_BASE_URL
        if model is None or model == DEFAULT_QWEN_MODEL:
            model = DEFAULT_DEEPSEEK_MODEL
        return DeepSeekModelGateway(
            api_key=settings.model_api_key,
            model=model,
            endpoint=deepseek_endpoint_from_base_url(endpoint_base),
            max_tokens=settings.model_max_tokens,
            thinking_mode=settings.model_thinking_mode,
            max_retries=retries,
            opener=opener or urlopen,
            cost_per_1k_input=cost_per_1k_input,
            cost_per_1k_output=cost_per_1k_output,
        )
    if provider == "fake":
        return FakeModelGateway()
    raise ModelConfigurationError("MODEL_UNKNOWN_PROVIDER")


__all__ = ["create_model_gateway"]
