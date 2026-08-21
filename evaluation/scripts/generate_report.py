"""Generate a safe Markdown report from an evaluation output directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def generate_report(run_dir: Path) -> Path:
    manifest = _read(run_dir / "run-manifest.json")
    metrics = _read(run_dir / "metrics.json")
    errors = _count_errors(run_dir / "errors.jsonl")
    usage = manifest.get("usage", {})
    lines = [
        f"# Evaluation report: {manifest.get('run_id', 'unknown')}",
        "",
        "This report contains aggregate results only; it intentionally excludes "
        "contract context and raw model responses.",
        "",
        "## Reproduction manifest",
        "",
        f"- Dataset: `{manifest.get('dataset_id')}` / `{manifest.get('dataset_version')}`",
        f"- Dataset SHA-256: `{manifest.get('dataset_sha256')}`",
        f"- Split and mode: `{manifest.get('split')}` / `{manifest.get('mode')}`",
        f"- Provider/model: `{manifest.get('provider')}` / `{manifest.get('model')}`",
        f"- Prompt/schema/mapping: `{manifest.get('prompt_version')}` / "
        f"`{manifest.get('schema_version')}` / `{manifest.get('mapping_version')}`",
        f"- Git commit: `{manifest.get('git_commit')}`",
        f"- Calls: `{usage.get('request_count', 0)}`; "
        f"input tokens: `{usage.get('token_input', 0)}`; "
        f"output tokens: `{usage.get('token_output', 0)}`",
        f"- Actual cost: `{usage.get('actual_cost')}`; "
        f"estimated cost: `{usage.get('estimated_cost')}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Provider failures",
        "",
        f"- Error records: `{errors}`",
        f"- Summary: `{json.dumps(manifest.get('error_summary', {}), sort_keys=True)}`",
        "",
        "## Interpretation limits",
        "",
        "CUAD is an English public clause/span benchmark and may be affected by "
        "model pretraining contamination. It does not prove the six Chinese "
        "contract categories, all seven product fields, or Chinese contract risk "
        "metrics. Product projection metrics are scoped to explicitly mapped "
        "CUAD categories only; no product total F1 or Phase 15 pass conclusion "
        "is emitted.",
        "",
        "A complete official CUAD test run must be explicitly authorized and was "
        "not started by this asset batch.",
        "",
    ]
    output = run_dir / "report.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path.name}")
    return value


def _count_errors(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        print(generate_report(args.run_dir))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
