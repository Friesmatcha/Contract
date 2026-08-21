"""Run CUAD native or explicitly scoped product-projection evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.config import Settings
from backend.app.integrations.model.factory import create_model_gateway
from backend.app.integrations.model.gateway import ModelGateway, ModelGatewayError
from backend.app.integrations.model.schemas import ExtractionRequest
from evaluation.adapters.cuad_adapter import load_samples, select_contracts
from evaluation.metrics.span_matching import DEFAULT_JACCARD_THRESHOLD, evaluate_spans
from evaluation.scripts.common import git_commit, load_mapping, resolve_dataset, write_json
from evaluation.scripts.generate_report import generate_report

PROMPT_VERSION = "cuad-native-prompt-v1"
SCHEMA_VERSION = "cuad-evaluation-schema-v1"
SANITIZATION_VERSION = "sanitization-v1"
MAX_PREDICTION_TEXT = 2000


class RequestBudgetExceeded(RuntimeError):
    """Raised before an opener makes a provider request above the run budget."""


class RequestBudgetOpener:
    def __init__(self, maximum: int) -> None:
        if maximum < 1:
            raise ValueError("maximum request budget must be positive")
        self.maximum = maximum
        self.count = 0

    def __call__(self, request: Any, *, timeout: float) -> Any:
        if self.count >= self.maximum:
            raise RequestBudgetExceeded("provider request budget reached")
        self.count += 1
        from urllib.request import urlopen

        return urlopen(request, timeout=timeout)


def evaluate(
    *,
    dataset_id: str,
    split: str,
    mode: str,
    provider: str,
    limit_contracts: int | None,
    limit_samples: int | None,
    max_requests: int | None,
    raw_dir: Path | None,
    output_root: Path,
) -> Path:
    started_at = datetime.now(UTC)
    dataset = resolve_dataset(dataset_id, raw_dir=raw_dir)
    if split not in dataset.split_files:
        raise ValueError(f"split is not available: {split}")
    samples = select_contracts(
        load_samples(dataset.split_files[split], split=split, dataset_id=dataset_id),
        limit_contracts,
    )
    if limit_samples is not None:
        if limit_samples < 1:
            raise ValueError("--limit-samples must be positive")
        samples = samples[:limit_samples]
    if not samples:
        raise ValueError("evaluation selected no samples")
    if provider in {"qwen", "deepseek"} and max_requests is None:
        raise ValueError(f"--max-requests is required for provider {provider}")
    if provider not in {"fake", "qwen", "deepseek"}:
        raise ValueError(f"unsupported provider: {provider}")

    mapping = load_mapping()
    mapping_version = str(mapping.get("mapping_version", "unknown"))
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    predictions: dict[str, list[dict[str, Any]]] = {}
    errors_path = run_dir / "errors.jsonl"
    error_summary: Counter[str] = Counter()
    telemetry: list[Any] = []
    provider_request_ids: list[str] = []
    budget: RequestBudgetOpener | None = None
    if provider in {"qwen", "deepseek"}:
        assert max_requests is not None
        budget = RequestBudgetOpener(max_requests)
    gateway = (
        _real_gateway(provider, budget)
        if provider in {"qwen", "deepseek"} and budget is not None
        else None
    )
    failed_samples = 0
    stopped = False

    with errors_path.open("w", encoding="utf-8", newline="\n") as errors_file:
        for sample in samples:
            sample_id = str(sample["sample_id"])
            if stopped:
                failed_samples += 1
                error_summary["provider_failure"] += 1
                _write_error(
                    errors_file,
                    sample,
                    code="REQUEST_LIMIT_REACHED",
                    provider_request_id=None,
                )
                continue
            if provider == "fake":
                predictions[sample_id] = _fake_prediction(sample)
                continue
            assert gateway is not None
            try:
                result = gateway.extract(_request(sample))
            except RequestBudgetExceeded:
                stopped = True
                failed_samples += 1
                error_summary["provider_failure"] += 1
                _write_error(
                    errors_file,
                    sample,
                    code="REQUEST_LIMIT_REACHED",
                    provider_request_id=None,
                )
                continue
            except ModelGatewayError as exc:
                failed_samples += 1
                category = _error_bucket(exc.code)
                error_summary[category] += 1
                error_summary["provider_failure"] += 1
                telemetry.extend(exc.telemetry)
                _write_error(
                    errors_file,
                    sample,
                    code=exc.code,
                    provider_request_id=exc.provider_request_id,
                    error=exc,
                )
                for item in exc.telemetry:
                    if item.provider_request_id:
                        provider_request_ids.append(item.provider_request_id)
                continue
            telemetry.extend(result.telemetry)
            for item in result.telemetry:
                if item.provider_request_id:
                    provider_request_ids.append(item.provider_request_id)
            predictions[sample_id] = _prediction_from_output(sample, result.output)

    _write_predictions(run_dir / "predictions.jsonl", samples, predictions)
    metrics = evaluate_spans(samples, predictions, threshold=DEFAULT_JACCARD_THRESHOLD)
    if mode == "cuad-product-projection":
        metrics = _project_metrics(metrics, samples, predictions, mapping)
    usage = _usage(telemetry, request_count=budget.count if budget else 0)
    error_summary.update({"failed_samples": failed_samples, "selected_samples": len(samples)})
    finished_at = datetime.now(UTC)
    manifest = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset.version,
        "dataset_sha256": dataset.sha256,
        "split": split,
        "mode": mode,
        "provider": provider,
        "model": gateway.model if gateway else "fake-cuad-v1",
        "endpoint_region": _endpoint_region(gateway) if gateway else None,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "max_tokens": (
            gateway.max_tokens
            if gateway is not None and hasattr(gateway, "max_tokens")
            else None
        ),
        "thinking_mode": (
            gateway.thinking_mode
            if gateway is not None and hasattr(gateway, "thinking_mode")
            else None
        ),
        "mapping_version": mapping_version,
        "git_commit": git_commit(),
        "rule_bundle_version": None,
        "template_version": None,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "counts": {
            "selected_samples": len(samples),
            "selected_contracts": len({sample["document_id"] for sample in samples}),
            "completed_samples": len(samples) - failed_samples,
            "failed_samples": failed_samples,
            "provider_failure_rate": failed_samples / len(samples),
            "complete_official_evaluation": False,
        },
        "usage": usage,
        "provider_request_ids": provider_request_ids[:1000],
        "error_summary": dict(error_summary),
        "request_limit": max_requests,
    }
    write_json(run_dir / "run-manifest.json", manifest)
    write_json(run_dir / "metrics.json", metrics)
    _write_metrics_csv(run_dir / "metrics.csv", metrics)
    generate_report(run_dir)
    print(
        json.dumps(
            {"run_dir": str(run_dir.relative_to(output_root.parent)), "run_id": run_id},
            sort_keys=True,
        )
    )
    return run_dir


def _real_gateway(provider: str, budget: RequestBudgetOpener) -> ModelGateway:
    settings = Settings(
        database_url="postgresql+psycopg://evaluation:unused@localhost/evaluation",
        redis_url="redis://localhost:6379/0",
    )
    selected = settings.model_copy(update={"model_provider": provider})
    return create_model_gateway(
        selected,
        opener=budget,
        max_retries=0,
        cost_per_1k_input=_decimal_env("MODEL_COST_PER_1K_INPUT"),
        cost_per_1k_output=_decimal_env("MODEL_COST_PER_1K_OUTPUT"),
    )


def _request(sample: dict[str, Any]) -> ExtractionRequest:
    return ExtractionRequest(
        input_text=str(sample["question"]),
        input_version=f"{sample['dataset_id']}-{sample['split']}",
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sanitization_policy_version=SANITIZATION_VERSION,
        context={
            "contract_id": str(sample["document_id"]),
            "question_id": str(sample["question_id"]),
            "category": str(sample["category"]),
            "contract_text": str(sample["context"]),
            "answer_instruction": (
                "Return field_key answer with value null for no answer; "
                "quote only answer spans."
            ),
        },
    )


def _prediction_from_output(sample: dict[str, Any], output: Any) -> list[dict[str, Any]]:
    texts: list[tuple[str, float]] = []
    for field in output.fields:
        field_key = field.field_key.casefold()
        if field_key in {"answer", "answers", "span", "spans", "clause"}:
            for value in _value_texts(field.value):
                texts.append((value, field.confidence))
            for evidence in field.evidence:
                texts.append((evidence.quote, field.confidence))
    for evidence in output.evidence:
        texts.append((evidence.quote, 0.5))
    answers: list[dict[str, Any]] = []
    seen: set[str] = set()
    context = str(sample["context"])
    for raw_text, score in texts:
        text = raw_text.strip()[:MAX_PREDICTION_TEXT]
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        start = context.find(text)
        answers.append(
            {
                "text": text,
                "start_offset": start if start >= 0 else None,
                "end_offset": start + len(text) if start >= 0 else None,
                "score": max(0.0, min(1.0, float(score))),
            }
        )
    return answers


def _value_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, str)]
    return []


def _fake_prediction(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "text": answer["text"],
            "start_offset": answer["start_offset"],
            "end_offset": answer["end_offset"],
            "score": 1.0,
        }
        for answer in sample["gold_answers"]
    ]


def _write_error(
    handle: Any,
    sample: dict[str, Any],
    *,
    code: str,
    provider_request_id: str | None,
    error: ModelGatewayError | None = None,
) -> None:
    diagnostic = {
        "http_status": error.http_status if error else None,
        "provider_error_code": error.provider_error_code if error else None,
        "retry_after_seconds": error.retry_after_seconds if error else None,
        "error_class": error.error_class if error else None,
        "provider_message": error.provider_message if error else None,
    }
    handle.write(
        json.dumps(
            {
                "sample_id": sample["sample_id"],
                "document_id": sample["document_id"],
                "category": sample["category"],
                "error_code": code,
                "provider_request_id": provider_request_id,
                **diagnostic,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _write_predictions(
    path: Path,
    samples: list[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for sample in samples:
            row = {
                "sample_id": sample["sample_id"],
                "document_id": sample["document_id"],
                "question_id": sample["question_id"],
                "category": sample["category"],
                "predictions": predictions.get(str(sample["sample_id"]), []),
            }
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _error_bucket(code: str) -> str:
    if code == "MODEL_TIMEOUT":
        return "timeout"
    if code == "MODEL_RATE_LIMITED":
        return "429"
    if code == "MODEL_PROVIDER_5XX":
        return "5xx"
    if code in {"MODEL_INVALID_JSON", "MODEL_EMPTY_RESPONSE"}:
        return "invalid_json"
    if code in {
        "MODEL_SCHEMA_INVALID",
        "MODEL_UNKNOWN_FIELDS",
        "MODEL_EVIDENCE_MISSING",
        "MODEL_PROVIDER_INVALID_RESPONSE",
        "MODEL_PROVIDER_RESPONSE_TOO_LARGE",
    }:
        return "schema_failure"
    return "other"


def _usage(telemetry: list[Any], *, request_count: int) -> dict[str, Any]:
    input_tokens = sum(item.token_input or 0 for item in telemetry)
    output_tokens = sum(item.token_output or 0 for item in telemetry)
    total_tokens = sum(item.token_total or 0 for item in telemetry)
    cache_hit_tokens = sum(item.cache_hit_tokens or 0 for item in telemetry)
    costs = [item.cost for item in telemetry if item.cost is not None]
    actual_cost = str(sum(costs, Decimal("0"))) if costs else None
    input_rate = _decimal_env("MODEL_COST_PER_1K_INPUT")
    output_rate = _decimal_env("MODEL_COST_PER_1K_OUTPUT")
    estimated_cost = None
    if input_rate is not None and output_rate is not None:
        estimated_cost = str(
            Decimal(input_tokens) / Decimal(1000) * input_rate
            + Decimal(output_tokens) / Decimal(1000) * output_rate
        )
    return {
        "request_count": request_count,
        "token_input": input_tokens,
        "token_output": output_tokens,
        "token_total": total_tokens or None,
        "cache_hit_tokens": cache_hit_tokens or None,
        "actual_cost": actual_cost,
        "estimated_cost": estimated_cost,
    }


def _project_metrics(
    native_metrics: dict[str, Any],
    samples: list[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    exact = {str(item["cuad_category"]) for item in mapping.get("exact", [])}
    partial = {str(item["cuad_category"]) for item in mapping.get("partial", [])}
    supported = exact | partial
    projected_samples = [sample for sample in samples if sample["category"] in supported]
    projected = evaluate_spans(projected_samples, predictions) if projected_samples else None
    return {
        "mode": "cuad-product-projection",
        "mapping_version": mapping.get("mapping_version"),
        "disclaimer": mapping.get("disclaimer"),
        "exact_categories": sorted(exact),
        "partial_categories": sorted(partial),
        "unsupported_categories": sorted(
            str(item["cuad_category"]) for item in mapping.get("unsupported", [])
        ),
        "projected_sample_count": len(projected_samples),
        "projected_span_metrics": projected,
        "native_metrics_all_samples": native_metrics,
        "product_total_f1": None,
    }


def _write_metrics_csv(path: Path, metrics: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for category, values in metrics.get("per_category", {}).items():
        rows.append({"scope": "category", "category": category, **values})
    for scope in ("micro", "macro"):
        values = metrics.get(scope)
        if isinstance(values, dict):
            rows.append({"scope": scope, "category": "", **values})
    if "projected_span_metrics" in metrics and isinstance(metrics["projected_span_metrics"], dict):
        for category, values in metrics["projected_span_metrics"].get("per_category", {}).items():
            rows.append({"scope": "projected_category", "category": category, **values})
    fieldnames = ["scope", "category", "support", "prediction_count", "precision", "recall", "f1"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _decimal_env(name: str) -> Decimal | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal environment value: {name}") from exc
    if value < 0:
        raise ValueError(f"environment value must be non-negative: {name}")
    return value


def _endpoint_region(gateway: ModelGateway) -> str | None:
    endpoint = getattr(gateway, "endpoint", None)
    return urlparse(endpoint).hostname if isinstance(endpoint, str) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, choices=("cuad-v1", "cuad-mini"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--mode", required=True, choices=("cuad-native", "cuad-product-projection"))
    parser.add_argument("--provider", required=True, choices=("fake", "qwen", "deepseek"))
    parser.add_argument("--limit-contracts", type=int)
    parser.add_argument("--limit-samples", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("evaluation/outputs"))
    args = parser.parse_args()
    try:
        evaluate(
            dataset_id=args.dataset,
            split=args.split,
            mode=args.mode,
            provider=args.provider,
            limit_contracts=args.limit_contracts,
            limit_samples=args.limit_samples,
            max_requests=args.max_requests,
            raw_dir=args.raw_dir,
            output_root=args.output_root,
        )
    except (KeyError, OSError, ValueError, ModelGatewayError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
