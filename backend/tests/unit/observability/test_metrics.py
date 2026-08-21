from decimal import Decimal
from uuid import uuid4

from backend.app.observability.metrics import metrics_response, observe_model_call
from backend.app.shared.model_telemetry import ModelCallTelemetry


def test_model_metrics_use_safe_low_cardinality_labels_and_expose_no_prompt() -> None:
    observe_model_call(
        ModelCallTelemetry(
            organization_id=uuid4(),
            review_task_id=uuid4(),
            stage_run_id=uuid4(),
            capability="classification",
            provider="fake",
            model="fake-model-v1",
            model_fingerprint="a" * 64,
            prompt_version="prompt-v1",
            response_schema_version="schema-v1",
            sanitization_policy_version="sanitization-v1",
            request_fingerprint="b" * 64,
            provider_request_id=None,
            status="succeeded",
            token_input=10,
            token_output=4,
            cost=Decimal("0.12"),
            latency_ms=20,
        )
    )
    body = metrics_response().body.decode("utf-8")
    assert (
        'contract_model_tokens_total{direction="input",model="fake-model-v1",provider="fake"}'
        in body
    )
    assert 'contract_model_cost_total{model="fake-model-v1",provider="fake"}' in body
    assert "prompt-v1" not in body
    assert "organization_id=\"" not in body
