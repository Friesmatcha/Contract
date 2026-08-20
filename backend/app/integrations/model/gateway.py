import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from backend.app.integrations.model.schemas import (
    ClassificationRequest,
    ClassificationResult,
    ClauseComparisonRequest,
    ClauseComparisonResult,
    ExtractionRequest,
    ExtractionResult,
    ModelCapability,
    ModelRequest,
    ModelResult,
    RiskAnalysisRequest,
    RiskAnalysisResult,
)
from backend.app.shared.model_telemetry import (
    ModelCallContext,
    ModelCallStatus,
    ModelCallTelemetry,
    model_fingerprint,
    model_request_fingerprint,
)

logger = logging.getLogger(__name__)


class ModelGatewayError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider_request_id = provider_request_id
        self.telemetry: tuple[ModelCallTelemetry, ...] = ()
        super().__init__(code)


class ModelConfigurationError(ModelGatewayError):
    def __init__(self) -> None:
        super().__init__("MODEL_ENVIRONMENT_NOT_CONFIGURED")


class ModelOutputError(ModelGatewayError):
    pass


class ModelTimeoutError(ModelGatewayError):
    def __init__(self, provider_request_id: str | None = None) -> None:
        super().__init__("MODEL_TIMEOUT", retryable=True, provider_request_id=provider_request_id)


class ModelConnectionError(ModelGatewayError):
    def __init__(self, provider_request_id: str | None = None) -> None:
        super().__init__(
            "MODEL_CONNECTION_ERROR", retryable=True, provider_request_id=provider_request_id
        )


class ModelRateLimitError(ModelGatewayError):
    def __init__(
        self,
        retry_after_seconds: float | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            "MODEL_RATE_LIMITED",
            retryable=True,
            retry_after_seconds=retry_after_seconds,
            provider_request_id=provider_request_id,
        )


class ModelServerError(ModelGatewayError):
    def __init__(self, provider_request_id: str | None = None) -> None:
        super().__init__(
            "MODEL_PROVIDER_5XX", retryable=True, provider_request_id=provider_request_id
        )


@dataclass(frozen=True, slots=True)
class RawModelResponse:
    content: str
    provider_request_id: str | None = None
    token_input: int | None = None
    token_output: int | None = None
    cost: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ModelInvocationResult[T: ModelResult]:
    output: T
    telemetry: tuple[ModelCallTelemetry, ...]


class ModelGateway(ABC):
    """Provider-neutral boundary for the four model capabilities."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        backoff_base_seconds: float = 1.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.provider = provider
        self.model = model
        self.max_retries = max_retries
        self._sleep = sleep
        self.backoff_base_seconds = backoff_base_seconds

    def classify(
        self,
        request: ClassificationRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelInvocationResult[ClassificationResult]:
        return self._invoke(
            request, ClassificationResult, capability="classification", context=context
        )

    def extract(
        self,
        request: ExtractionRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelInvocationResult[ExtractionResult]:
        return self._invoke(request, ExtractionResult, capability="extraction", context=context)

    def analyze_risk(
        self,
        request: RiskAnalysisRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelInvocationResult[RiskAnalysisResult]:
        return self._invoke(
            request, RiskAnalysisResult, capability="risk_analysis", context=context
        )

    def compare_clauses(
        self,
        request: ClauseComparisonRequest,
        *,
        context: ModelCallContext | None = None,
    ) -> ModelInvocationResult[ClauseComparisonResult]:
        return self._invoke(
            request,
            ClauseComparisonResult,
            capability="clause_comparison",
            context=context,
        )

    @abstractmethod
    def _raw_call(
        self,
        request: ModelRequest,
        *,
        capability: ModelCapability,
        repair: bool,
    ) -> RawModelResponse:
        """Make one provider call. It must never log or persist the request body."""

    def _invoke[T: ModelResult](
        self,
        request: ModelRequest,
        result_type: type[T],
        *,
        capability: ModelCapability,
        context: ModelCallContext | None,
    ) -> ModelInvocationResult[T]:
        if context is not None and context.capability != capability:
            raise ValueError("model call context capability does not match the gateway method")
        request_fp = model_request_fingerprint(request, capability=capability)
        model_fp = model_fingerprint(
            provider=self.provider,
            model=self.model,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
        )
        telemetry: list[ModelCallTelemetry] = []
        raw = self._call_with_retries(
            request,
            capability=capability,
            request_fp=request_fp,
            model_fp=model_fp,
            telemetry=telemetry,
            repair=False,
            context=context,
        )
        try:
            output = _parse_model_output(raw.content, result_type)
        except ModelOutputError as exc:
            _mark_output_failure(telemetry, exc.code)
            raw = self._call_with_retries(
                request,
                capability=capability,
                request_fp=request_fp,
                model_fp=model_fp,
                telemetry=telemetry,
                repair=True,
                context=context,
            )
            try:
                output = _parse_model_output(raw.content, result_type)
            except ModelOutputError as repair_exc:
                _mark_output_failure(telemetry, repair_exc.code)
                repair_exc.telemetry = tuple(telemetry)
                raise repair_exc from None

        logger.info(
            "model_call_completed",
            extra={
                "duration_ms": sum(item.latency_ms for item in telemetry),
                "error_class": None,
            },
        )
        return ModelInvocationResult(output=output, telemetry=tuple(telemetry))

    def _call_with_retries(
        self,
        request: ModelRequest,
        *,
        capability: ModelCapability,
        request_fp: str,
        model_fp: str,
        telemetry: list[ModelCallTelemetry],
        repair: bool,
        context: ModelCallContext | None,
    ) -> RawModelResponse:
        retry_no = 0
        attempt_no = 1
        while True:
            started = perf_counter()
            try:
                raw = self._raw_call(request, capability=capability, repair=repair)
            except ModelGatewayError as exc:
                latency_ms = max(0, round((perf_counter() - started) * 1000))
                telemetry.append(
                    _telemetry(
                        request=request,
                        request_fp=request_fp,
                        model_fp=model_fp,
                        provider=self.provider,
                        model=self.model,
                        attempt_no=attempt_no,
                        repair=repair,
                        status=(
                            "retryable"
                            if exc.retryable and retry_no < self.max_retries
                            else "failed"
                        ),
                        error_code=exc.code,
                        provider_request_id=exc.provider_request_id,
                        latency_ms=latency_ms,
                        context=context,
                        capability=capability,
                    )
                )
                if not exc.retryable or retry_no >= self.max_retries:
                    exc.telemetry = tuple(telemetry)
                    raise
                self._sleep(_retry_delay(self.backoff_base_seconds, retry_no, exc))
                retry_no += 1
                attempt_no += 1
                continue

            latency_ms = max(0, round((perf_counter() - started) * 1000))
            telemetry.append(
                _telemetry(
                    request=request,
                    request_fp=request_fp,
                    model_fp=model_fp,
                    provider=self.provider,
                    model=self.model,
                    attempt_no=attempt_no,
                    repair=repair,
                    status="succeeded",
                    provider_request_id=raw.provider_request_id,
                    token_input=raw.token_input,
                    token_output=raw.token_output,
                    cost=raw.cost,
                    latency_ms=latency_ms,
                    context=context,
                    capability=capability,
                )
            )
            return raw


def _parse_model_output[T: ModelResult](content: str, result_type: type[T]) -> T:
    try:
        payload: Any = json.loads(content)
    except (TypeError, ValueError):
        raise ModelOutputError("MODEL_INVALID_JSON") from None
    if not isinstance(payload, dict):
        raise ModelOutputError("MODEL_SCHEMA_INVALID")
    try:
        return result_type.model_validate(payload)
    except ValidationError as exc:
        error_types = {str(error.get("type")) for error in exc.errors()}
        if "extra_forbidden" in error_types:
            code = "MODEL_UNKNOWN_FIELDS"
        elif any("evidence" in str(error.get("loc")) for error in exc.errors()):
            code = "MODEL_EVIDENCE_MISSING"
        else:
            code = "MODEL_SCHEMA_INVALID"
        raise ModelOutputError(code) from None


def _mark_output_failure(telemetry: list[ModelCallTelemetry], code: str) -> None:
    if telemetry:
        telemetry[-1].status = "failed"
        telemetry[-1].error_code = code
        telemetry[-1].error_class = "model_output"


def _retry_delay(base: float, retry_no: int, error: ModelGatewayError) -> float:
    if error.retry_after_seconds is not None:
        return max(0.0, error.retry_after_seconds)
    return max(0.0, base * (2.0**retry_no))


def _telemetry(
    *,
    request: ModelRequest,
    request_fp: str,
    model_fp: str,
    provider: str,
    model: str,
    attempt_no: int,
    repair: bool,
    status: ModelCallStatus,
    error_code: str | None = None,
    provider_request_id: str | None = None,
    token_input: int | None = None,
    token_output: int | None = None,
    cost: Decimal | None = None,
    latency_ms: int = 0,
    context: ModelCallContext | None = None,
    capability: ModelCapability,
) -> ModelCallTelemetry:
    return ModelCallTelemetry(
        organization_id=context.organization_id if context else None,
        review_task_id=context.review_task_id if context else None,
        stage_run_id=context.stage_run_id if context else None,
        capability=capability,
        provider=provider,
        model=model,
        model_fingerprint=model_fp,
        prompt_version=request.prompt_version,
        response_schema_version=request.schema_version,
        sanitization_policy_version=request.sanitization_policy_version,
        request_fingerprint=request_fp,
        provider_request_id=provider_request_id,
        status=status,
        token_input=token_input,
        token_output=token_output,
        cost=cost,
        latency_ms=latency_ms,
        error_code=error_code,
        error_class=None,
        attempt_no=attempt_no,
        repair_attempt=repair,
    )


__all__ = [
    "ModelCallContext",
    "ModelConfigurationError",
    "ModelConnectionError",
    "ModelGateway",
    "ModelGatewayError",
    "ModelInvocationResult",
    "ModelOutputError",
    "ModelRateLimitError",
    "ModelServerError",
    "ModelTimeoutError",
    "RawModelResponse",
]
