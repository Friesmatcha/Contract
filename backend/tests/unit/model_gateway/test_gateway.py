import json
from io import BytesIO
from secrets import token_urlsafe
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

import pytest
from pydantic import SecretStr

from backend.app.integrations.model.fake import (
    FakeModelGateway,
    FakeResponse,
    fake_failure,
)
from backend.app.integrations.model.gateway import (
    ModelGatewayError,
    ModelOutputError,
    ModelServerError,
    RawModelResponse,
)
from backend.app.integrations.model.qwen import (
    DEFAULT_QWEN_ENDPOINT,
    QwenModelGateway,
    qwen_endpoint_from_base_url,
)
from backend.app.integrations.model.schemas import (
    ClassificationRequest,
    ClauseComparisonRequest,
    ExtractionRequest,
    ModelRequest,
    RiskAnalysisRequest,
)
from backend.app.shared.model_telemetry import (
    ModelCallContext,
    model_fingerprint,
    model_request_fingerprint,
)


def _classification() -> dict[str, object]:
    return {
        "category": "other",
        "confidence": 0.8,
        "evidence": [{"source_span_id": "span-1", "quote": "脱敏证据"}],
    }


def _request(request_type: type[ClassificationRequest] = ClassificationRequest) -> object:
    return request_type(input_text="脱敏合同输入", input_version="document-v1")


def _context(capability: str = "classification") -> ModelCallContext:
    return ModelCallContext(
        organization_id=uuid4(),
        review_task_id=uuid4(),
        stage_run_id=uuid4(),
        capability=capability,
    )


def _test_secret() -> SecretStr:
    return SecretStr(token_urlsafe(32))


def test_fake_implements_all_four_capability_methods() -> None:
    gateway = FakeModelGateway()

    assert gateway.classify(_request()).output.category == "other"
    assert gateway.extract(_request(ExtractionRequest)).output.fields
    assert gateway.analyze_risk(_request(RiskAnalysisRequest)).output.findings
    assert gateway.compare_clauses(_request(ClauseComparisonRequest)).output.comparisons


def test_transient_retry_uses_retry_after_and_records_usage() -> None:
    sleeps: list[float] = []
    gateway = FakeModelGateway(
        fixtures={
            "classification": [
                fake_failure("429", retry_after_seconds=7),
                FakeResponse(
                    _classification(),
                    provider_request_id="provider-request-1",
                    token_input=20,
                    token_output=9,
                ),
            ]
        },
        max_retries=2,
        sleep=sleeps.append,
    )

    result = gateway.classify(_request(), context=_context())

    assert sleeps == [7]
    assert [item.status for item in result.telemetry] == ["retryable", "succeeded"]
    assert result.telemetry[-1].provider_request_id == "provider-request-1"
    assert result.telemetry[-1].token_input == 20
    assert result.telemetry[-1].token_output == 9
    assert result.telemetry[-1].cost is not None


def test_context_capability_must_match_gateway_method() -> None:
    gateway = FakeModelGateway()

    with pytest.raises(ValueError, match="capability"):
        gateway.classify(_request(), context=_context("extraction"))

    assert gateway.calls == []


def test_transient_retry_is_bounded_and_non_retryable_error_is_not_retried() -> None:
    gateway = FakeModelGateway(
        fixtures={
            "classification": [
                fake_failure("5xx"),
                fake_failure("5xx"),
                fake_failure("5xx"),
            ]
        },
        max_retries=2,
    )

    with pytest.raises(ModelServerError) as error_info:
        gateway.classify(_request())

    assert len(gateway.calls) == 3
    assert len(error_info.value.telemetry) == 3
    assert [item.status for item in error_info.value.telemetry] == [
        "retryable",
        "retryable",
        "failed",
    ]


@pytest.mark.parametrize("failure_kind", ["timeout", "connection"])
def test_timeout_and_connection_errors_are_retryable(failure_kind: str) -> None:
    gateway = FakeModelGateway(
        fixtures={
            "classification": [
                fake_failure(failure_kind),
                FakeResponse(_classification()),
            ]
        },
        max_retries=1,
    )

    result = gateway.classify(_request())

    assert result.output.category == "other"
    assert result.telemetry[0].error_code in {
        "MODEL_TIMEOUT",
        "MODEL_CONNECTION_ERROR",
    }


def test_non_retryable_provider_error_is_not_retried() -> None:
    class NonRetryableFake(FakeModelGateway):
        def _raw_call(
            self,
            request: ModelRequest,
            *,
            capability: str,
            repair: bool,
        ) -> RawModelResponse:
            raise ModelGatewayError("MODEL_PROVIDER_REQUEST_FAILED")

    gateway = NonRetryableFake(max_retries=3)
    with pytest.raises(ModelGatewayError) as error_info:
        gateway.classify(_request())

    assert len(gateway.calls) == 0
    assert error_info.value.code == "MODEL_PROVIDER_REQUEST_FAILED"


@pytest.mark.parametrize(
    ("failure_kind", "error_code"),
    [
        ("invalid_json", "MODEL_INVALID_JSON"),
        ("schema_mismatch", "MODEL_SCHEMA_INVALID"),
        ("unknown_fields", "MODEL_UNKNOWN_FIELDS"),
        ("no_evidence", "MODEL_EVIDENCE_MISSING"),
    ],
)
def test_output_error_gets_exactly_one_repair_retry(
    failure_kind: str, error_code: str
) -> None:
    gateway = FakeModelGateway(
        fixtures={"classification": [fake_failure(failure_kind), fake_failure(failure_kind)]}
    )

    with pytest.raises(ModelOutputError) as error_info:
        gateway.classify(_request())

    assert error_info.value.code == error_code
    assert gateway.calls == [("classification", False), ("classification", True)]
    assert [item.repair_attempt for item in error_info.value.telemetry] == [False, True]


def test_output_error_repair_can_succeed_once() -> None:
    gateway = FakeModelGateway(
        fixtures={"classification": [fake_failure("invalid_json"), _classification()]}
    )

    result = gateway.classify(_request())

    assert result.output.category == "other"
    assert gateway.calls == [("classification", False), ("classification", True)]


def test_fingerprint_is_deterministic_and_changes_with_input_version() -> None:
    first = _request()
    same = _request()
    changed = ClassificationRequest(input_text="脱敏合同输入", input_version="document-v2")

    assert model_request_fingerprint(first) == model_request_fingerprint(same)
    assert model_request_fingerprint(first) != model_request_fingerprint(changed)
    assert model_request_fingerprint(first, capability="classification") != (
        model_request_fingerprint(first, capability="extraction")
    )
    assert model_fingerprint(
        provider="qwen", model="model-v1", prompt_version="p1", schema_version="s1"
    ) != model_fingerprint(
        provider="qwen", model="model-v2", prompt_version="p1", schema_version="s1"
    )


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.headers = {"X-Request-ID": "qwen-provider-1"}
        self._body = json.dumps(payload).encode()

    def read(self, _size: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_qwen_adapter_contract_is_offline_and_records_provider_usage() -> None:
    captured: list[object] = []

    def opener(request: object, *, timeout: float) -> _FakeHttpResponse:
        captured.append((request, timeout))
        return _FakeHttpResponse(
            {
                "id": "qwen-envelope-1",
                "choices": [
                    {"message": {"content": json.dumps(_classification())}}
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 10},
            }
        )

    gateway = QwenModelGateway(
        api_key=_test_secret(),
        model="qwen-test",
        opener=opener,
        sleep=lambda _seconds: None,
    )
    result = gateway.classify(_request(), context=_context())

    assert result.output.category == "other"
    assert result.telemetry[-1].provider_request_id == "qwen-envelope-1"
    assert result.telemetry[-1].token_input == 21
    assert result.telemetry[-1].token_output == 10
    request, _ = captured[0]
    assert isinstance(request, Request)
    assert request.data is not None
    request_body = json.loads(request.data.decode("utf-8"))
    assert request_body["messages"][0]["content"].startswith("Capability: classification.")
    assert "Allowed root keys are category, confidence, evidence" in (
        request_body["messages"][0]["content"]
    )
    assert "no Markdown, commentary, or extra keys" in request_body["messages"][0]["content"]
    assert captured


def test_qwen_endpoint_uses_qwencloud_documented_region() -> None:
    assert DEFAULT_QWEN_ENDPOINT == (
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert qwen_endpoint_from_base_url(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ) == DEFAULT_QWEN_ENDPOINT


def test_qwen_429_retry_after_is_offline() -> None:
    calls = 0
    sleeps: list[float] = []

    def opener(_request: object, *, timeout: float) -> _FakeHttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                "https://example.invalid",
                429,
                "rate limited",
                {"Retry-After": "5", "X-Request-ID": "qwen-429"},
                BytesIO(b"not logged"),
            )
        return _FakeHttpResponse(
            {
                "choices": [{"message": {"content": json.dumps(_classification())}}],
                "usage": {},
            }
        )

    gateway = QwenModelGateway(
        api_key=_test_secret(),
        model="qwen-test",
        opener=opener,
        sleep=sleeps.append,
    )
    result = gateway.classify(_request())

    assert result.output.category == "other"
    assert sleeps == [5]
    assert result.telemetry[0].error_code == "MODEL_RATE_LIMITED"


def test_qwen_configuration_error_does_not_expose_secret() -> None:
    secret = token_urlsafe(32)
    with pytest.raises(Exception) as error_info:
        QwenModelGateway(api_key=SecretStr(secret), model=None)

    assert secret not in str(error_info.value)
    assert "MODEL_ENVIRONMENT_NOT_CONFIGURED" in str(error_info.value)


def test_gateway_log_does_not_contain_input_or_provider_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = token_urlsafe(32)
    caplog.set_level("INFO")
    gateway = QwenModelGateway(
        api_key=SecretStr(secret),
        model="qwen-test",
        opener=lambda _request, timeout: _FakeHttpResponse(
            {"choices": [{"message": {"content": json.dumps(_classification())}}]}
        ),
        sleep=lambda _seconds: None,
    )
    gateway.classify(
        ClassificationRequest(input_text="contract-full-text-do-not-log")
    )

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "contract-full-text-do-not-log" not in messages
    assert secret not in messages
