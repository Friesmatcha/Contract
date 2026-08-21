import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pydantic import SecretStr

from backend.app.integrations.model.deepseek import (
    DEFAULT_DEEPSEEK_ENDPOINT,
    MAX_PROVIDER_RESPONSE_BYTES,
    DeepSeekModelGateway,
    deepseek_endpoint_from_base_url,
)
from backend.app.integrations.model.gateway import ModelGatewayError
from backend.app.integrations.model.schemas import (
    ClassificationRequest,
    ClauseComparisonRequest,
    ExtractionRequest,
    RiskAnalysisRequest,
)

SECRET = "deepseek-test-secret-must-not-leak"


def _classification() -> dict[str, object]:
    return {
        "category": "other",
        "confidence": 0.8,
        "evidence": [{"source_span_id": "span-1", "quote": "脱敏证据"}],
    }


class _Response:
    def __init__(self, payload: object, *, request_id: str = "deepseek-request-1") -> None:
        self.headers = {"X-Request-ID": request_id}
        if isinstance(payload, bytes):
            self._body = payload
        elif isinstance(payload, str):
            self._body = payload.encode("utf-8")
        else:
            self._body = json.dumps(payload).encode("utf-8")

    def read(self, _size: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _gateway(opener: object, *, max_retries: int = 0) -> DeepSeekModelGateway:
    return DeepSeekModelGateway(
        api_key=SecretStr(SECRET),
        model="deepseek-v4-flash",
        endpoint="https://api.deepseek.com/",
        max_tokens=1234,
        max_retries=max_retries,
        opener=opener,  # type: ignore[arg-type]
        sleep=lambda _seconds: None,
    )


def test_deepseek_endpoint_is_normalized_without_duplicate_path() -> None:
    assert DEFAULT_DEEPSEEK_ENDPOINT == "https://api.deepseek.com/chat/completions"
    assert deepseek_endpoint_from_base_url("https://api.deepseek.com/") == DEFAULT_DEEPSEEK_ENDPOINT
    assert (
        deepseek_endpoint_from_base_url("https://api.deepseek.com/chat/completions/")
        == DEFAULT_DEEPSEEK_ENDPOINT
    )


def test_deepseek_request_uses_json_mode_thinking_and_configured_limit() -> None:
    captured: list[Request] = []

    def opener(request: Request, *, timeout: float) -> _Response:
        captured.append(request)
        return _Response(
            {
                "id": "deepseek-envelope-1",
                "choices": [{"message": {"content": json.dumps(_classification())}}],
                "usage": {
                    "prompt_tokens": 21,
                    "completion_tokens": 10,
                    "total_tokens": 31,
                    "prompt_cache_hit_tokens": 5,
                },
            }
        )

    result = _gateway(opener).classify(ClassificationRequest(input_text="脱敏合同输入"))

    assert result.output.category == "other"
    assert result.telemetry[-1].provider == "deepseek"
    assert result.telemetry[-1].provider_request_id == "deepseek-envelope-1"
    assert result.telemetry[-1].token_input == 21
    assert result.telemetry[-1].token_output == 10
    assert result.telemetry[-1].token_total == 31
    assert result.telemetry[-1].cache_hit_tokens == 5
    body = json.loads(captured[0].data.decode("utf-8"))
    assert captured[0].full_url == DEFAULT_DEEPSEEK_ENDPOINT
    assert captured[0].get_header("Authorization") == f"Bearer {SECRET}"
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 1234
    assert "stream" not in body
    assert "temperature" not in body


@pytest.mark.parametrize(
    ("request_type", "capability"),
    [
        (ClassificationRequest, "classification"),
        (ExtractionRequest, "extraction"),
        (RiskAnalysisRequest, "risk_analysis"),
        (ClauseComparisonRequest, "clause_comparison"),
    ],
)
def test_every_capability_prompt_has_json_contract_and_example(
    request_type: type[object], capability: str
) -> None:
    request = request_type(input_text="脱敏合同输入")  # type: ignore[call-arg]
    messages = DeepSeekModelGateway._messages(
        request, capability=capability, repair=False  # type: ignore[arg-type]
    )
    prompt = messages[0]["content"]
    assert "Return exactly one JSON object." in prompt
    assert "JSON" in prompt
    assert "Example JSON output:" in prompt
    assert "Prompt version:" in prompt
    assert "Schema version:" in prompt


def test_empty_content_is_classified_and_uses_one_repair_call() -> None:
    calls = 0

    def opener(_request: Request, *, timeout: float) -> _Response:
        nonlocal calls
        calls += 1
        return _Response(
            {"choices": [{"message": {"content": ""}}]}
            if calls == 1
            else {"choices": [{"message": {"content": json.dumps(_classification())}}]}
        )

    result = _gateway(opener).classify(ClassificationRequest(input_text="脱敏合同输入"))

    assert result.output.category == "other"
    assert calls == 2
    assert result.telemetry[0].error_code == "MODEL_EMPTY_RESPONSE"
    assert result.telemetry[1].repair_attempt is True


def test_missing_choices_and_oversized_response_fail_without_repair() -> None:
    for response in (
        _Response({"id": "missing-choices"}),
        _Response(b"x" * (MAX_PROVIDER_RESPONSE_BYTES + 1)),
    ):
        def opener(
            _request: Request, *, timeout: float, response: _Response = response
        ) -> _Response:
            return response

        with pytest.raises(ModelGatewayError) as error_info:
            _gateway(opener).classify(
                ClassificationRequest(input_text="脱敏合同输入")
            )
        assert error_info.value.code in {
            "MODEL_PROVIDER_INVALID_RESPONSE",
            "MODEL_PROVIDER_RESPONSE_TOO_LARGE",
        }
        assert error_info.value.telemetry == (error_info.value.telemetry[0],)


def test_invalid_json_repair_is_bounded_to_one_call() -> None:
    captured: list[Request] = []

    def opener(request: Request, *, timeout: float) -> _Response:
        captured.append(request)
        return _Response(
            "not-json"
            if len(captured) == 1
            else {"choices": [{"message": {"content": json.dumps(_classification())}}]}
        )

    result = _gateway(opener).classify(ClassificationRequest(input_text="脱敏合同输入"))

    assert result.output.category == "other"
    assert len(captured) == 2
    repair_prompt = json.loads(captured[1].data.decode("utf-8"))["messages"][0]["content"]
    assert "previous response failed strict validation" in repair_prompt


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "MODEL_PROVIDER_INVALID_REQUEST"),
        (401, "MODEL_PROVIDER_AUTHENTICATION_FAILED"),
        (402, "MODEL_PROVIDER_INSUFFICIENT_BALANCE"),
        (403, "MODEL_PROVIDER_PERMISSION_DENIED"),
        (404, "MODEL_PROVIDER_NOT_FOUND"),
        (429, "MODEL_RATE_LIMITED"),
        (500, "MODEL_PROVIDER_5XX"),
    ],
)
def test_http_errors_are_mapped_without_provider_secret(status: int, expected: str) -> None:
    def opener(_request: Request, *, timeout: float) -> _Response:
        raise HTTPError(
            DEFAULT_DEEPSEEK_ENDPOINT,
            status,
            "provider error",
            {"X-Request-ID": "deepseek-error-1", "Retry-After": "5"},
            BytesIO(
                json.dumps(
                    {"error": {"code": "provider_code", "message": f"Bearer {SECRET}"}}
                ).encode()
            ),
        )

    with pytest.raises(ModelGatewayError) as error_info:
        _gateway(opener).classify(ClassificationRequest(input_text="脱敏合同输入"))

    error = error_info.value
    assert error.code == expected
    assert error.provider_request_id == "deepseek-error-1"
    assert error.provider_message == "Bearer [REDACTED]"
    assert SECRET not in str(error)
    if status == 429:
        assert error.retry_after_seconds == 5
    assert error.http_status == status


@pytest.mark.parametrize("failure", [TimeoutError(), URLError("connection failed")])
def test_timeout_and_connection_failure_are_safe(failure: Exception) -> None:
    def opener(_request: Request, *, timeout: float) -> _Response:
        raise failure

    with pytest.raises(ModelGatewayError) as error_info:
        _gateway(opener).classify(ClassificationRequest(input_text="脱敏合同输入"))

    assert error_info.value.code in {"MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR"}
    assert SECRET not in str(error_info.value)


def test_gateway_does_not_log_contract_text_or_api_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    gateway = _gateway(
        lambda _request, timeout: _Response(
            {"choices": [{"message": {"content": json.dumps(_classification())}}]}
        )
    )
    gateway.classify(ClassificationRequest(input_text="contract-full-text-do-not-log"))

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "contract-full-text-do-not-log" not in messages
    assert SECRET not in messages


def test_configuration_error_does_not_expose_secret() -> None:
    with pytest.raises(ModelGatewayError) as error_info:
        DeepSeekModelGateway(api_key=SecretStr(SECRET), model=None)

    assert SECRET not in str(error_info.value)
    assert error_info.value.code == "MODEL_ENVIRONMENT_NOT_CONFIGURED"
