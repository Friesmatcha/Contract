import json
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.app.integrations.model.gateway import (
    ModelConnectionError,
    ModelGateway,
    ModelGatewayError,
    ModelRateLimitError,
    ModelServerError,
    ModelTimeoutError,
    RawModelResponse,
)
from backend.app.integrations.model.schemas import ModelCapability, ModelRequest


@dataclass(frozen=True, slots=True)
class FakeResponse:
    payload: dict[str, Any] | str
    provider_request_id: str | None = None
    token_input: int | None = 12
    token_output: int | None = 8
    cost: Decimal | None = Decimal("0.00010000")


@dataclass(frozen=True, slots=True)
class FakeFailure:
    kind: str
    retry_after_seconds: float | None = None


def fake_failure(kind: str, *, retry_after_seconds: float | None = None) -> FakeFailure:
    return FakeFailure(kind=kind, retry_after_seconds=retry_after_seconds)


class FakeModelGateway(ModelGateway):
    """Deterministic gateway used by unit, contract and integration tests."""

    def __init__(
        self,
        *,
        fixtures: Mapping[
            ModelCapability, Iterable[FakeResponse | FakeFailure | dict[str, Any] | str]
        ]
        | None = None,
        max_retries: int = 3,
        sleep: Any = None,
        provider: str = "fake",
        model: str = "fake-model-v1",
    ) -> None:
        super().__init__(
            provider=provider,
            model=model,
            max_retries=max_retries,
            sleep=sleep or (lambda _seconds: None),
        )
        self._fixtures: dict[str, deque[Any]] = defaultdict(deque)
        for capability, values in (fixtures or {}).items():
            self._fixtures[capability].extend(values)
        self.calls: list[tuple[str, bool]] = []

    def enqueue(self, capability: ModelCapability, *values: Any) -> None:
        self._fixtures[capability].extend(values)

    def _raw_call(
        self,
        request: ModelRequest,
        *,
        capability: ModelCapability,
        repair: bool,
    ) -> RawModelResponse:
        self.calls.append((capability, repair))
        item = (
            self._fixtures[capability].popleft()
            if self._fixtures[capability]
            else _success(capability)
        )
        if isinstance(item, FakeFailure):
            if item.kind in {"invalid_json", "schema_mismatch", "unknown_fields", "no_evidence"}:
                return _raw(FakeResponse(_output_failure_payload(item.kind, capability)))
            raise _failure(item)
        if isinstance(item, FakeResponse):
            return _raw(item)
        if isinstance(item, dict):
            return _raw(FakeResponse(item))
        return _raw(FakeResponse(item))


def _raw(response: FakeResponse) -> RawModelResponse:
    content = (
        json.dumps(response.payload, ensure_ascii=False, separators=(",", ":"))
        if isinstance(response.payload, dict)
        else response.payload
    )
    return RawModelResponse(
        content=content,
        provider_request_id=response.provider_request_id,
        token_input=response.token_input,
        token_output=response.token_output,
        cost=response.cost,
    )


def _failure(failure: FakeFailure) -> ModelGatewayError:
    if failure.kind == "timeout":
        return ModelTimeoutError()
    if failure.kind == "connection":
        return ModelConnectionError()
    if failure.kind == "429":
        return ModelRateLimitError(failure.retry_after_seconds)
    if failure.kind == "5xx":
        return ModelServerError()
    raise ValueError(f"unknown fake failure kind: {failure.kind}")


def _output_failure_payload(kind: str, capability: str) -> dict[str, Any] | str:
    if kind == "invalid_json":
        return "{invalid-json"
    if kind == "schema_mismatch":
        return {"evidence": [{"source_span_id": "span-1", "quote": "脱敏证据"}]}
    if kind == "unknown_fields":
        payload = _success(capability).payload
        if isinstance(payload, dict):
            return {**payload, "extra": True}
    payload = _success(capability).payload
    if isinstance(payload, dict):
        return {**payload, "evidence": []}
    return payload


def _success(capability: str) -> FakeResponse:
    evidence = [{"source_span_id": "span-1", "quote": "脱敏证据"}]
    payload: dict[str, Any]
    if capability == "classification":
        payload = {"category": "other", "confidence": 0.5, "evidence": evidence}
    elif capability == "extraction":
        payload = {
            "fields": [
                {
                    "field_key": "effective_date",
                    "value": None,
                    "confidence": 0.5,
                    "evidence": evidence,
                }
            ],
            "evidence": evidence,
        }
    elif capability == "risk_analysis":
        payload = {
            "findings": [
                {
                    "risk_type": "other",
                    "severity": "low",
                    "title": "待复核",
                    "basis": "脱敏依据",
                    "evidence": evidence,
                }
            ],
            "evidence": evidence,
        }
    else:
        payload = {
            "comparisons": [
                {
                    "clause_key": "general",
                    "result": "not_applicable",
                    "explanation": "待复核",
                    "evidence": evidence,
                }
            ],
            "evidence": evidence,
        }
    return FakeResponse(payload=payload, provider_request_id=f"fake-{capability}-1")


__all__ = ["FakeFailure", "FakeModelGateway", "FakeResponse", "fake_failure"]
