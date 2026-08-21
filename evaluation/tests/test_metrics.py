from __future__ import annotations

from typing import Any

import pytest

from evaluation.metrics.classification_metrics import classification_report
from evaluation.metrics.span_matching import (
    evaluate_spans,
    jaccard_similarity,
    normalize_text,
    span_match,
)


def test_normalization_and_jaccard_are_deterministic() -> None:
    assert normalize_text("  Parties,  HERE! ") == "parties here"
    assert jaccard_similarity("alpha beta", "beta gamma") == pytest.approx(1 / 3)
    assert span_match("Acme, Corp.", "acme corp", category="Parties")
    assert span_match("Acme and Beta", "Acme", category="Parties")


def test_span_metrics_include_no_answer_and_do_not_pseudo_pass_empty_input() -> None:
    samples: list[dict[str, Any]] = [
        {"sample_id": "a", "category": "Parties", "gold_answers": [{"text": "Acme"}]},
        {"sample_id": "b", "category": "Governing Law", "gold_answers": []},
        {"sample_id": "c", "category": "Governing Law", "gold_answers": [{"text": "New York"}]},
    ]
    predictions = {
        "a": [{"text": "Acme", "score": 0.9}],
        "b": [],
        "c": [{"text": "California", "score": 0.8}],
    }
    result = evaluate_spans(samples, predictions)
    assert result["micro"]["precision"] == pytest.approx(0.5)
    assert result["micro"]["recall"] == pytest.approx(0.5)
    assert result["no_answer_accuracy"] == 1.0
    assert result["per_category"]["Parties"]["f1"] == 1.0
    with pytest.raises(ValueError, match="empty"):
        evaluate_spans([], {})


def test_classification_metrics_have_zero_safe_empty_label_set() -> None:
    result = classification_report([], [])
    assert result["accuracy"] == 0.0
    assert result["macro"]["f1"] == 0.0
