"""Validate CUAD SQuAD structure, offsets, IDs, and answer semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters.cuad_adapter import validate_split_files
from evaluation.scripts.common import resolve_dataset, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="cuad-v1", choices=("cuad-v1", "cuad-mini"))
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        dataset = resolve_dataset(args.dataset, raw_dir=args.raw_dir)
        summary = validate_split_files(dataset.split_files, dataset_id=args.dataset)
    except (OSError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    summary["dataset_version"] = dataset.version
    summary["dataset_sha256"] = dataset.sha256
    if args.output:
        write_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
