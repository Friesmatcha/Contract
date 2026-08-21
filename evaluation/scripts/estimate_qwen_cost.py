"""Estimate CUAD Qwen requests and cost without calling a provider."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters.cuad_adapter import load_samples, select_contracts
from evaluation.scripts.common import resolve_dataset

PROMPT_OVERHEAD_CHARS = 700
CHARS_PER_TOKEN = 4
EXPECTED_OUTPUT_TOKENS = 120


def estimate(
    samples: list[dict[str, Any]],
    *,
    input_rate: Decimal | None,
    output_rate: Decimal | None,
) -> dict[str, Any]:
    input_tokens = sum(
        math.ceil(
            (
                len(str(sample["context"]))
                + len(str(sample["question"]))
                + PROMPT_OVERHEAD_CHARS
            )
            / CHARS_PER_TOKEN
        )
        for sample in samples
    )
    output_tokens = len(samples) * EXPECTED_OUTPUT_TOKENS
    estimated_cost = None
    if input_rate is not None and output_rate is not None:
        estimated_cost = str(
            (Decimal(input_tokens) / Decimal(1000)) * input_rate
            + (Decimal(output_tokens) / Decimal(1000)) * output_rate
        )
    return {
        "sample_count": len(samples),
        "contract_count": len({sample["document_id"] for sample in samples}),
        "request_count": len(samples),
        "input_tokens_estimate": input_tokens,
        "output_tokens_estimate": output_tokens,
        "assumptions": {
            "chars_per_token": CHARS_PER_TOKEN,
            "prompt_overhead_chars": PROMPT_OVERHEAD_CHARS,
            "expected_output_tokens_per_request": EXPECTED_OUTPUT_TOKENS,
            "retry_and_repair_calls_included": False,
        },
        "input_rate_per_1k": str(input_rate) if input_rate is not None else None,
        "output_rate_per_1k": str(output_rate) if output_rate is not None else None,
        "estimated_cost": estimated_cost,
        "cost_note": (
            "Set MODEL_COST_PER_1K_INPUT and MODEL_COST_PER_1K_OUTPUT or pass rates "
            "for a monetary estimate."
        ),
    }


def _rate(argument: str | None, environment_name: str) -> Decimal | None:
    raw = argument or os.environ.get(environment_name)
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"invalid cost rate: {environment_name}") from exc
    if value < 0:
        raise ValueError(f"cost rate must be non-negative: {environment_name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="cuad-v1", choices=("cuad-v1", "cuad-mini"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--input-rate-per-1k")
    parser.add_argument("--output-rate-per-1k")
    args = parser.parse_args()
    try:
        dataset = resolve_dataset(args.dataset, raw_dir=args.raw_dir)
        samples = select_contracts(
            load_samples(
                dataset.split_files[args.split], split=args.split, dataset_id=args.dataset
            ),
            None,
        )
        result = estimate(
            samples,
            input_rate=_rate(args.input_rate_per_1k, "MODEL_COST_PER_1K_INPUT"),
            output_rate=_rate(args.output_rate_per_1k, "MODEL_COST_PER_1K_OUTPUT"),
        )
        result.update(
            {
                "dataset_id": args.dataset,
                "dataset_version": dataset.version,
                "dataset_sha256": dataset.sha256,
                "split": args.split,
            }
        )
    except (KeyError, OSError, ValueError) as exc:
        print(f"estimate failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
