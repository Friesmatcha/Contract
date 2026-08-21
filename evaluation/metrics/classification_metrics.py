"""Small metric primitives shared by the independent evaluation code."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    return {
        "precision": precision,
        "recall": recall,
        "f1": safe_divide(2 * precision * recall, precision + recall),
    }


def classification_report(
    gold: Sequence[str], predicted: Sequence[str], labels: Iterable[str] | None = None
) -> dict[str, Any]:
    if len(gold) != len(predicted):
        raise ValueError("gold and predicted labels must have equal length")
    label_values = sorted(set(labels or ()) | set(gold) | set(predicted))
    per_label: dict[str, Any] = {}
    total_tp = total_fp = total_fn = 0
    for label in label_values:
        pairs = zip(gold, predicted, strict=True)
        tp = sum(actual == label and guess == label for actual, guess in pairs)
        pairs = zip(gold, predicted, strict=True)
        fp = sum(actual != label and guess == label for actual, guess in pairs)
        pairs = zip(gold, predicted, strict=True)
        fn = sum(actual == label and guess != label for actual, guess in pairs)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        per_label[label] = {"support": gold.count(label), **prf(tp, fp, fn)}
    macro = {
        key: safe_divide(sum(item[key] for item in per_label.values()), len(per_label))
        for key in ("precision", "recall", "f1")
    }
    return {
        "accuracy": safe_divide(
            sum(a == b for a, b in zip(gold, predicted, strict=True)), len(gold)
        ),
        "micro": prf(total_tp, total_fp, total_fn),
        "macro": macro,
        "per_label": per_label,
        "support": len(gold),
        "confusion": {label: count for label, count in Counter(gold).items()},
    }


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float:
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have equal length")
    positive_count = sum(labels)
    if not positive_count:
        return 0.0
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    true_positives = 0
    precision_sum = 0.0
    for rank, index in enumerate(order, start=1):
        if labels[index]:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positive_count


__all__ = ["average_precision", "classification_report", "prf", "safe_divide"]
