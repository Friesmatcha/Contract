from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from backend.app.shared.model_telemetry import ModelCallTelemetry

HTTP_REQUESTS = Counter(
    "contract_http_requests_total", "Completed HTTP requests.", ("method", "route", "status_code")
)
HTTP_LATENCY = Histogram(
    "contract_http_request_duration_seconds", "HTTP request duration.", ("method", "route")
)
REVIEW_STAGE_RUNS = Counter(
    "contract_review_stage_runs_total", "Review stage outcomes.", ("stage", "status")
)
REVIEW_STAGE_LATENCY = Histogram(
    "contract_review_stage_duration_seconds", "Review stage duration.", ("stage",)
)
OCR_PAGES = Counter("contract_ocr_pages_total", "OCR page outcomes.", ("status",))
MODEL_CALLS = Counter(
    "contract_model_calls_total",
    "Model call outcomes.",
    ("provider", "model", "capability", "status"),
)
MODEL_TOKENS = Counter(
    "contract_model_tokens_total", "Model tokens consumed.", ("provider", "model", "direction")
)
MODEL_COST = Counter(
    "contract_model_cost_total", "Model cost reported by the provider.", ("provider", "model")
)
MODEL_LATENCY = Histogram(
    "contract_model_call_duration_seconds",
    "Model call duration.",
    ("provider", "model", "capability"),
)
WARNING_EVENTS = Counter(
    "contract_warning_events_total", "Warning events and creation outcomes.", ("event",)
)
REPORT_OUTCOMES = Counter(
    "contract_report_outcomes_total", "Report generation outcomes.", ("status",)
)


def observe_http_request(*, method: str, route: str, status_code: int, duration_ms: float) -> None:
    HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
    HTTP_LATENCY.labels(method, route).observe(max(0.0, duration_ms / 1000))


def observe_review_stage(*, stage: str, status: str, duration_ms: int | None = None) -> None:
    REVIEW_STAGE_RUNS.labels(stage, status).inc()
    if duration_ms is not None:
        REVIEW_STAGE_LATENCY.labels(stage).observe(max(0.0, duration_ms / 1000))


def observe_ocr_page(status: str) -> None:
    OCR_PAGES.labels(status).inc()


def observe_model_call(telemetry: ModelCallTelemetry) -> None:
    labels = (telemetry.provider, telemetry.model, telemetry.capability or "unknown")
    MODEL_CALLS.labels(*labels, telemetry.status).inc()
    if telemetry.token_input is not None:
        MODEL_TOKENS.labels(telemetry.provider, telemetry.model, "input").inc(telemetry.token_input)
    if telemetry.token_output is not None:
        MODEL_TOKENS.labels(telemetry.provider, telemetry.model, "output").inc(
            telemetry.token_output
        )
    if telemetry.cost is not None:
        MODEL_COST.labels(telemetry.provider, telemetry.model).inc(float(telemetry.cost))
    MODEL_LATENCY.labels(*labels).observe(max(0.0, telemetry.latency_ms / 1000))


def observe_warning_event(event: str) -> None:
    WARNING_EVENTS.labels(event).inc()


def observe_report_outcome(status: str) -> None:
    REPORT_OUTCOMES.labels(status).inc()


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "metrics_response",
    "observe_http_request",
    "observe_model_call",
    "observe_ocr_page",
    "observe_report_outcome",
    "observe_review_stage",
    "observe_warning_event",
]
