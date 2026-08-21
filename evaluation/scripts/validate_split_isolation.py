"""Verify that one contract cannot occur in multiple dataset splits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters.cuad_adapter import load_samples
from evaluation.scripts.common import resolve_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="cuad-v1", choices=("cuad-v1", "cuad-mini"))
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args()
    try:
        dataset = resolve_dataset(args.dataset, raw_dir=args.raw_dir)
        owners: dict[str, str] = {}
        for split, path in dataset.split_files.items():
            for sample in load_samples(path, split=split, dataset_id=args.dataset):
                document_id = str(sample["document_id"])
                prior = owners.setdefault(document_id, split)
                if prior != split:
                    raise ValueError(f"document occurs in {prior} and {split}")
    except (OSError, ValueError) as exc:
        print(f"split isolation failed: {exc}", file=sys.stderr)
        return 1
    result = {
        "dataset_id": args.dataset,
        "splits": sorted(dataset.split_files),
        "documents": len(owners),
        "isolated": True,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
