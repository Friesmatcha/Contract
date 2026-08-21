from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.adapters.cuad_adapter import DatasetValidationError, validate_split_files


def _write(path: Path, title: str) -> None:
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "title": title,
                        "paragraphs": [
                            {
                                "context": "The contract has no answer.",
                                "qas": [
                                    {
                                        "id": path.stem + "-q1",
                                        "question": "Question",
                                        "is_impossible": True,
                                        "answers": [],
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


def test_split_isolation_rejects_same_document_in_train_and_test(tmp_path: Path) -> None:
    train = tmp_path / "train.json"
    test = tmp_path / "test.json"
    _write(train, "same-contract")
    _write(test, "same-contract")
    with pytest.raises(DatasetValidationError, match="multiple splits"):
        validate_split_files({"train": train, "test": test}, dataset_id="cuad-mini")
