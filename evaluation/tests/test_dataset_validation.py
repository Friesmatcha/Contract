from __future__ import annotations

from pathlib import Path

from evaluation.adapters.cuad_adapter import validate_split_files


def test_fixture_validation_reports_counts_without_context() -> None:
    summary = validate_split_files(
        {"test": Path("evaluation/datasets/fixtures/cuad-mini/test.json")},
        dataset_id="cuad-mini",
    )
    assert summary["total_samples"] == 5
    assert summary["total_documents"] == 5
    assert summary["splits"]["test"]["no_answer_samples"] == 1
    assert "context" not in summary
