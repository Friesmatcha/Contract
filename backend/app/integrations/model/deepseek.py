"""DeepSeek OpenAI-compatible ModelGateway implementation."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_ENDPOINT = f"{DEFAULT_DEEPSEEK_BASE_URL}/chat/completions"
MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_PROVIDER_ERROR_MESSAGE = 512

_OUTPUT_CONTRACTS: dict[ModelCapability, str] = {
    "classification": (
        "Example JSON output: {\"category\":\"purchase\",\"confidence\":0.95,"
        "\"evidence\":[{\"source_span_id\":\"span_001\",\"quote\":\"...\"}]}"
    ),
    "extraction": (
        "Example JSON output: {\"fields\":[{\"field_key\":\"contract_amount\","
        "\"value\":\"100000 CNY\",\"confidence\":0.95,\"evidence\":[]}],"
        "\"evidence\":[]}"
    ),
    "risk_analysis": (
        "Example JSON output: {\"findings\":[{\"risk_type\":\"liability\","
        "\"severity\":\"low\",\"title\":\"Example\",\"basis\":\"Example\","
        "\"evidence\":[{\"source_span_id\":\"span_001\",\"quote\":\"...\"}]}],"
        "\"evidence\":[]}"
    ),
    "clause_comparison": (
        "Example JSON output: {\"comparisons\":[{\"clause_key\":\"payment\","
        "\"result\":\"match\",\"explanation\":\"Example\",\"evidence\":[]}],"
        "\"evidence\":[]}"
    ),
}


class _Response(Protocol):
    headers: Any

    def read(self, size: int = -1) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: Any) -> None: ...


class DeepSeekModelGateway(ModelGateway):
    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        model: str | None,
        endpoint: str = DEFAULT_DEEPSEEK_ENDPOINT,
        max_tokens: int = 2048,
        thinking_mode: Literal["disabled", "enabled"] = "disabled",
        timeout_seconds: float = 60,
        max_retries: int = 3,
        opener: Callable[..., _Response] = urlopen,
        sleep: Callable[[float], None] | None = None,
        backoff_base_seconds: float = 1.0,
        cost_per_1k_input: Decimal | None = None,
        cost_per_1k_output: Decimal | None = None,
    ) -> None:
        normalized_endpoint = deepseek_endpoint_from_base_url(endpoint)
        parsed = urlparse(normalized_endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "endpoint must be an HTTPS URL without credentials, query, or fragment"
            )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_tokens < 1 or max_tokens > 384_000:
            raise ValueError("max_tokens must be between 1 and 384000")
        if thinking_mode not in {"disabled", "enabled"}:
            raise ValueError("thinking_mode must be disabled or enabled")
        if api_key is None or not api_key.get_secret_value().strip() or not model:
            raise ModelConfigurationError()
        super().__init__(
            provider="deepseek",
            model=model,
            max_retries=max_retries,
            sleep=sleep or time.sleep,
            backoff_base_seconds=backoff_base_seconds,
        )
        self._api_key = api_key
        self.endpoint = normalized_endpoint
        self.max_tokens = max_tokens
        self.thinking_mode = thinking_mode
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
            "thinking": {"type": self.thinking_mode},
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_tokens,
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

        provider_request_id = _header(headers, "X-Request-ID")
        if len(raw_body) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ModelGatewayError(
                "MODEL_PROVIDER_RESPONSE_TOO_LARGE",
                provider_request_id=provider_request_id,
                error_class="invalid_response",
            )
        text = raw_body.decode("utf-8", errors="replace")
        try:
            envelope: Any = json.loads(text)
        except (TypeError, ValueError):
            return RawModelResponse(content=text, provider_request_id=provider_request_id)
        if not isinstance(envelope, dict):
            return RawModelResponse(content=text, provider_request_id=provider_request_id)
        provider_request_id = _string_or_none(envelope.get("id")) or provider_request_id
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelGatewayError(
                "MODEL_PROVIDER_INVALID_RESPONSE",
                provider_request_id=provider_request_id,
                error_class="invalid_response",
            )
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelGatewayError(
                "MODEL_PROVIDER_INVALID_RESPONSE",
                provider_request_id=provider_request_id,
                error_class="invalid_response",
            )
        usage = envelope.get("usage")
        token_input, token_output, token_total, cache_hit_tokens = _usage(usage)
        return RawModelResponse(
            content=message["content"],
            provider_request_id=provider_request_id,
            token_input=token_input,
            token_output=token_output,
            token_total=token_total,
            cache_hit_tokens=cache_hit_tokens,
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
            f"Capability: {capability}. Return exactly one JSON object. "
            "Return only JSON matching the requested schema. Do not use Markdown code fences, "
            "explanations, multiple JSON objects, or unknown fields. "
            f"{_OUTPUT_CONTRACTS[capability]} "
            f"Prompt version: {request.prompt_version}. Schema version: {request.schema_version}."
        )
        if repair:
            instruction += (
                " The previous response failed strict validation. Regenerate it from scratch, "
                "remove every unknown key, and use only the allowed keys above."
            )
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


def deepseek_endpoint_from_base_url(base_url: str | None) -> str:
    normalized = (base_url or DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _http_error(error: HTTPError) -> ModelGatewayError:
    request_id = _header(error.headers, "X-Request-ID")
    retry_after = _retry_after(_header(error.headers, "Retry-After"))
    provider_error_code, provider_message = _provider_error_details(error)
    status = error.code
    if status == 429:
        return ModelRateLimitError(
            retry_after,
            request_id,
            http_status=status,
            provider_error_code=provider_error_code,
            provider_message=provider_message,
        )
    if status == 408:
        return ModelTimeoutError(
            request_id,
            http_status=status,
            provider_error_code=provider_error_code,
            provider_message=provider_message,
        )
    if 500 <= status <= 599:
        return ModelServerError(
            request_id,
            http_status=status,
            provider_error_code=provider_error_code,
            provider_message=provider_message,
        )
    code = {
        400: "MODEL_PROVIDER_INVALID_REQUEST",
        401: "MODEL_PROVIDER_AUTHENTICATION_FAILED",
        402: "MODEL_PROVIDER_INSUFFICIENT_BALANCE",
        403: "MODEL_PROVIDER_PERMISSION_DENIED",
        404: "MODEL_PROVIDER_NOT_FOUND",
        422: "MODEL_PROVIDER_INVALID_REQUEST",
    }.get(status, "MODEL_PROVIDER_REQUEST_FAILED")
    return ModelGatewayError(
        code,
        provider_request_id=request_id,
        http_status=status,
        provider_error_code=provider_error_code,
        provider_message=provider_message,
        error_class="provider_request",
    )


def _provider_error_details(error: HTTPError) -> tuple[str | None, str | None]:
    try:
        raw = error.read(4096)
    except OSError:
        return None, None
    try:
        payload: Any = json.loads(raw.decode("utf-8", errors="replace"))
    except (TypeError, ValueError):
        return None, None
    details = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(details, dict):
        return None, None
    code = _string_or_none(details.get("code")) or _string_or_none(details.get("type"))
    message = _safe_message(details.get("message"))
    return code, message


def _safe_message(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", value)
    sanitized = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1[REDACTED]", sanitized)
    return sanitized.strip()[:MAX_PROVIDER_ERROR_MESSAGE]


def _usage(value: Any) -> tuple[int | None, int | None, int | None, int | None]:
    if not isinstance(value, dict):
        return None, None, None, None
    input_tokens = _nonnegative_int(value.get("prompt_tokens"))
    output_tokens = _nonnegative_int(value.get("completion_tokens"))
    total_tokens = _nonnegative_int(value.get("total_tokens"))
    details = value.get("prompt_tokens_details")
    cache_hit = _nonnegative_int(value.get("prompt_cache_hit_tokens"))
    if cache_hit is None and isinstance(details, dict):
        cache_hit = _nonnegative_int(details.get("cached_tokens"))
    return input_tokens, output_tokens, total_tokens, cache_hit


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


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    value: Any = None
    if hasattr(headers, "items"):
        for key, candidate in headers.items():
            if str(key).casefold() == name.casefold():
                value = candidate
                break
    if isinstance(value, str) and value.strip():
        return value.strip()[:255]
    return None


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


__all__ = [
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_DEEPSEEK_ENDPOINT",
    "DeepSeekModelGateway",
    "MAX_PROVIDER_RESPONSE_BYTES",
    "deepseek_endpoint_from_base_url",
]
