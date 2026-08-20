import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import SecretStr

from backend.app.integrations.model.gateway import (
    ModelConfigurationError,
    ModelConnectionError,
    ModelGateway,
    ModelGatewayError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    RawModelResponse,
)
from backend.app.integrations.model.schemas import ModelCapability, ModelRequest

DEFAULT_QWEN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024


class _Response(Protocol):
    headers: Any

    def read(self, size: int = -1) -> bytes: ...

    def __enter__(self) -> "_Response": ...

    def __exit__(self, *args: Any) -> None: ...


class QwenModelGateway(ModelGateway):
    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        model: str | None,
        endpoint: str = DEFAULT_QWEN_ENDPOINT,
        timeout_seconds: float = 60,
        max_retries: int = 3,
        opener: Callable[..., _Response] = urlopen,
        sleep: Callable[[float], None] | None = None,
        backoff_base_seconds: float = 1.0,
        cost_per_1k_input: Decimal | None = None,
        cost_per_1k_output: Decimal | None = None,
    ) -> None:
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("endpoint must be an HTTP URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if api_key is None or not api_key.get_secret_value().strip() or not model:
            raise ModelConfigurationError()
        super().__init__(
            provider="qwen",
            model=model,
            max_retries=max_retries,
            sleep=sleep or time.sleep,
            backoff_base_seconds=backoff_base_seconds,
        )
        self._api_key = api_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output

    def _raw_call(
        self,
        request: ModelRequest,
        *,
        capability: ModelCapability,
        repair: bool,
    ) -> RawModelResponse:
        body = {
            "model": self.model,
            "messages": self._messages(request, capability=capability, repair=repair),
            "response_format": {"type": "json_object"},
        }
        provider_request = Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(provider_request, timeout=self.timeout_seconds) as response:
                raw_body = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                headers = response.headers
        except HTTPError as exc:
            raise _http_error(exc) from None
        except TimeoutError:
            raise ModelTimeoutError() from None
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ModelTimeoutError() from None
            raise ModelConnectionError() from None
        except OSError:
            raise ModelConnectionError() from None

        if len(raw_body) > MAX_PROVIDER_RESPONSE_BYTES:
            return RawModelResponse(
                content="{}", provider_request_id=_header(headers, "X-Request-ID")
            )
        text = raw_body.decode("utf-8", errors="replace")
        provider_request_id = _header(headers, "X-Request-ID")
        try:
            envelope: Any = json.loads(text)
        except (TypeError, ValueError):
            return RawModelResponse(content=text, provider_request_id=provider_request_id)
        if not isinstance(envelope, dict):
            return RawModelResponse(content=text, provider_request_id=provider_request_id)
        provider_request_id = _string_or_none(envelope.get("id")) or provider_request_id
        content = _message_content(envelope)
        usage = envelope.get("usage")
        token_input = (
            _nonnegative_int(usage.get("prompt_tokens"))
            if isinstance(usage, dict)
            else None
        )
        token_output = (
            _nonnegative_int(usage.get("completion_tokens")) if isinstance(usage, dict) else None
        )
        return RawModelResponse(
            content=content,
            provider_request_id=provider_request_id,
            token_input=token_input,
            token_output=token_output,
            cost=_cost(
                token_input,
                token_output,
                input_rate=self._cost_per_1k_input,
                output_rate=self._cost_per_1k_output,
            ),
        )

    @staticmethod
    def _messages(
        request: ModelRequest,
        *,
        capability: ModelCapability,
        repair: bool,
    ) -> list[dict[str, str]]:
        instruction = (
            f"Capability: {capability}. Return only a JSON object that matches the "
            "requested schema. "
            f"Prompt version: {request.prompt_version}. Schema version: {request.schema_version}."
        )
        if repair:
            instruction += " Repair the previous output: include at least one valid evidence item."
        return [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "input_version": request.input_version,
                        "input": request.input_text,
                        "context": request.context,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]


def _http_error(error: HTTPError) -> ModelGatewayError:
    request_id = _header(error.headers, "X-Request-ID")
    retry_after = _retry_after(_header(error.headers, "Retry-After"))
    if error.code == 429:
        return ModelRateLimitError(retry_after, request_id)
    if error.code == 408:
        return ModelTimeoutError(request_id)
    if error.code in range(500, 600):
        return ModelServerError(request_id)
    return ModelGatewayError("MODEL_PROVIDER_REQUEST_FAILED", provider_request_id=request_id)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        seconds = -1
    if seconds >= 0:
        return seconds
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _message_content(envelope: dict[str, Any]) -> str:
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _header(headers: Any, name: str) -> str | None:
    value = headers.get(name) if headers is not None else None
    return value.strip()[:255] if isinstance(value, str) and value.strip() else None


def _string_or_none(value: Any) -> str | None:
    return value.strip()[:255] if isinstance(value, str) and value.strip() else None


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _cost(
    token_input: int | None,
    token_output: int | None,
    *,
    input_rate: Decimal | None,
    output_rate: Decimal | None,
) -> Decimal | None:
    if token_input is None or token_output is None:
        return None
    if input_rate is None or output_rate is None:
        return None
    return (Decimal(token_input) / Decimal(1000)) * input_rate + (
        Decimal(token_output) / Decimal(1000)
    ) * output_rate


__all__ = ["DEFAULT_QWEN_ENDPOINT", "QwenModelGateway"]
