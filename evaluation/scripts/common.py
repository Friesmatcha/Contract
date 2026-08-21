"""Shared path and manifest helpers for evaluation CLIs."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.adapters.cuad_adapter import discover_split_files

yaml_module: Any = importlib.import_module("yaml")

ROOT = Path(__file__).resolve().parents[2]
CUAD_MANIFEST = ROOT / "evaluation" / "datasets" / "manifests" / "cuad-v1.yaml"
MAPPING_PATH = ROOT / "evaluation" / "mappings" / "cuad-product-mapping.yaml"


@dataclass(frozen=True, slots=True)
class Dataset:
    dataset_id: str
    version: str
    sha256: str
    split_files: dict[str, Path]


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml_module.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be an object: {path.name}")
    return value


def resolve_dataset(dataset_id: str, *, raw_dir: Path | None = None) -> Dataset:
    if dataset_id == "cuad-mini":
        path = ROOT / "evaluation" / "datasets" / "fixtures" / "cuad-mini" / "test.json"
        return Dataset(
            dataset_id=dataset_id,
            version="fixture-v1",
            sha256=sha256_file(path),
            split_files={"test": path},
        )
    if dataset_id != "cuad-v1":
        raise ValueError(f"unsupported dataset: {dataset_id}")
    manifest = load_yaml(CUAD_MANIFEST)
    archive_sha256 = manifest.get("archive_sha256")
    if not isinstance(archive_sha256, str) or len(archive_sha256) != 64:
        raise ValueError("CUAD archive_sha256 is not recorded; download and verify it first")
    root = raw_dir or CUAD_MANIFEST.parent.parent / "raw"
    extracted = root / str(manifest["extracted_dir"])
    split_files = discover_split_files(extracted)
    return Dataset(
        dataset_id="cuad-v1",
        version=str(manifest["dataset_version"]),
        sha256=archive_sha256,
        split_files=split_files,
    )


def load_mapping() -> dict[str, Any]:
    return load_yaml(MAPPING_PATH)


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "CUAD_MANIFEST",
    "Dataset",
    "MAPPING_PATH",
    "ROOT",
    "git_commit",
    "load_mapping",
    "load_yaml",
    "resolve_dataset",
    "sha256_file",
    "write_json",
]
