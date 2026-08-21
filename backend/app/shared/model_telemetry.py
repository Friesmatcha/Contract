import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

ModelCallStatus = Literal["succeeded", "retryable", "failed"]


@dataclass(frozen=True, slots=True)
class ModelCallContext:
    organization_id: UUID
    review_task_id: UUID
    stage_run_id: UUID
    capability: str


@dataclass(slots=True)
class ModelCallTelemetry:
    organization_id: UUID | None
    review_task_id: UUID | None
    stage_run_id: UUID | None
    capability: str | None
    provider: str
    model: str
    model_fingerprint: str
    prompt_version: str
    response_schema_version: str
    sanitization_policy_version: str
    request_fingerprint: str
    provider_request_id: str | None
    status: ModelCallStatus
    token_input: int | None = None
    token_output: int | None = None
    cost: Decimal | None = None
    latency_ms: int = 0
    error_code: str | None = None
    error_class: str | None = None
    attempt_no: int = 1
    repair_attempt: bool = False
    created_at: datetime | None = None


def model_request_fingerprint(request: Any, *, capability: str | None = None) -> str:
    payload = request.model_dump(mode="json")
    if capability is not None:
        payload = {"capability": capability, "request": payload}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def model_fingerprint(
    *, provider: str, model: str, prompt_version: str, schema_version: str
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def persist_model_call(
    session: Session,
    telemetry: ModelCallTelemetry,
    *,
    context: ModelCallContext,
) -> Any:
    from backend.app.modules.reviews.models import ModelCall
    from backend.app.observability.metrics import observe_model_call

    if telemetry.capability != context.capability:
        raise ValueError("model call telemetry capability does not match its context")
    if telemetry.request_fingerprint != telemetry.request_fingerprint.lower():
        raise ValueError("request fingerprint must be lowercase")
    row = ModelCall(
        organization_id=context.organization_id,
        review_task_id=context.review_task_id,
        stage_run_id=context.stage_run_id,
        capability=context.capability,
        provider=telemetry.provider,
        model=telemetry.model,
        model_fingerprint=telemetry.model_fingerprint,
        prompt_version=telemetry.prompt_version,
        response_schema_version=telemetry.response_schema_version,
        sanitization_policy_version=telemetry.sanitization_policy_version,
        request_fingerprint=telemetry.request_fingerprint,
        provider_request_id=telemetry.provider_request_id,
        status=telemetry.status,
        token_input=telemetry.token_input,
        token_output=telemetry.token_output,
        cost=telemetry.cost,
        latency_ms=telemetry.latency_ms,
        error_code=telemetry.error_code,
        error_class=telemetry.error_class,
        attempt_no=telemetry.attempt_no,
        repair_attempt=telemetry.repair_attempt,
    )
    session.add(row)
    observe_model_call(telemetry)
    return row


def persist_invocation(
    session: Session,
    telemetry: tuple[ModelCallTelemetry, ...],
    *,
    context: ModelCallContext,
) -> list[Any]:
    return [persist_model_call(session, item, context=context) for item in telemetry]


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ModelCallContext",
    "ModelCallTelemetry",
    "model_fingerprint",
    "model_request_fingerprint",
    "persist_invocation",
    "persist_model_call",
]
