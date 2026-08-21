from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.adapters.cuad_adapter import DatasetValidationError, load_samples, write_jsonl

FIXTURE = Path("evaluation/datasets/fixtures/cuad-mini/test.json")


def test_adapter_preserves_ids_categories_offsets_and_no_answer() -> None:
    samples = load_samples(FIXTURE, split="test", dataset_id="cuad-mini")
    assert len(samples) == 5
    assert {sample["document_id"] for sample in samples} == {
        "mini-party-1", "mini-law-1", "mini-date-1", "mini-conf-1", "mini-empty-1"
    }
    assert samples[0]["question_id"] == "mini-party-1-q1"
    assert samples[0]["category"] == "Parties"
    assert samples[-1]["gold_answers"] == []
    assert samples[0]["context"][26:49] == samples[0]["gold_answers"][0]["text"]


def test_adapter_rejects_bad_answer_offset(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["data"][0]["paragraphs"][0]["qas"][0]["answers"][0]["answer_start"] = 0
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="offset"):
        load_samples(path, split="test", dataset_id="cuad-mini")


def test_jsonl_output_is_normalized_and_counted(tmp_path: Path) -> None:
    samples = load_samples(FIXTURE, split="test", dataset_id="cuad-mini")
    output = tmp_path / "normalized.jsonl"
    assert write_jsonl(samples, output) == 5
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]["task"] == "clause_span_extraction"
    assert "context" in rows[0]


def test_adapter_extracts_category_from_official_cuad_question_shape(tmp_path: Path) -> None:
    path = tmp_path / "official-shape.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "title": "official-shape",
                        "paragraphs": [
                            {
                                "context": "The law is New York.",
                                "qas": [
                                    {
                                        "id": "official-q1",
                                        "question": (
                                            "Highlight the parts (if any) of this contract "
                                            'related to "Governing Law" that should be reviewed '
                                            "by a lawyer."
                                        ),
                                        "is_impossible": False,
                                        "answers": [
                                            {"text": "New York", "answer_start": 11}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    samples = load_samples(path, split="test", dataset_id="cuad-v1")
    assert samples[0]["category"] == "Governing Law"
