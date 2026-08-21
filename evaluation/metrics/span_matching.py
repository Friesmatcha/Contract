"""Independent CUAD span matching and precision-recall metrics."""

from __future__ import annotations

import string
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from evaluation.metrics.classification_metrics import average_precision, prf, safe_divide

DEFAULT_JACCARD_THRESHOLD = 0.5


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    normalized: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        normalized.append(
            " " if category.startswith("P") or character in string.punctuation else character
        )
    return " ".join("".join(normalized).split())


def token_set(value: str) -> set[str]:
    return set(normalize_text(value).split())


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def span_match(
    predicted: str,
    gold: str,
    *,
    category: str,
    threshold: float = DEFAULT_JACCARD_THRESHOLD,
) -> bool:
    if normalize_text(predicted) == normalize_text(gold):
        return True
    # CUAD Parties compatibility: one predicted party span may match any one
    # gold party span; it need not concatenate every party in the contract.
    if category.casefold() == "parties":
        predicted_tokens = token_set(predicted)
        gold_tokens = token_set(gold)
        return gold_tokens.issubset(predicted_tokens) or jaccard_similarity(
            predicted, gold
        ) >= threshold
    return jaccard_similarity(predicted, gold) >= threshold


def evaluate_spans(
    samples: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    threshold: float = DEFAULT_JACCARD_THRESHOLD,
) -> dict[str, Any]:
    if not samples:
        raise ValueError("cannot evaluate an empty sample set")
    category_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0, "support": 0, "predictions": 0}
    )
    sample_labels: list[bool] = []
    sample_scores: list[float] = []
    no_answer_correct = 0
    no_answer_total = 0

    for sample in samples:
        sample_id = str(sample["sample_id"])
        category = str(sample["category"])
        gold_answers = sample.get("gold_answers", [])
        predicted_answers = predictions.get(sample_id, ())
        if not isinstance(gold_answers, list):
            raise ValueError(f"gold_answers is not a list: {sample_id}")
        matched_gold: set[int] = set()
        true_positive = 0
        for predicted in predicted_answers:
            text = predicted.get("text")
            if not isinstance(text, str) or not text:
                continue
            match_index = next(
                (
                    index
                    for index, gold in enumerate(gold_answers)
                    if index not in matched_gold
                    and isinstance(gold, dict)
                    and isinstance(gold.get("text"), str)
                    and span_match(text, gold["text"], category=category, threshold=threshold)
                ),
                None,
            )
            if match_index is not None:
                matched_gold.add(match_index)
                true_positive += 1
        false_positive = max(0, len(predicted_answers) - true_positive)
        false_negative = max(0, len(gold_answers) - true_positive)
        counts = category_counts[category]
        counts["tp"] += true_positive
        counts["fp"] += false_positive
        counts["fn"] += false_negative
        counts["support"] += bool(gold_answers)
        counts["predictions"] += len(predicted_answers)
        gold_has_answer = bool(gold_answers)
        prediction_has_answer = bool(predicted_answers)
        no_answer_total += 1
        no_answer_correct += gold_has_answer == prediction_has_answer
        sample_labels.append(gold_has_answer)
        sample_scores.append(
            max((_score(item) for item in predicted_answers), default=0.0)
        )

    category_metrics = {
        category: {
            "support": counts["support"],
            "prediction_count": counts["predictions"],
            **prf(counts["tp"], counts["fp"], counts["fn"]),
        }
        for category, counts in sorted(category_counts.items())
    }
    micro_counts = {
        key: sum(counts[key] for counts in category_counts.values())
        for key in ("tp", "fp", "fn")
    }
    macro = {
        key: safe_divide(
            sum(metric[key] for metric in category_metrics.values()), len(category_metrics)
        )
        for key in ("precision", "recall", "f1")
    }
    return {
        "sample_count": len(samples),
        "category_count": len(category_metrics),
        "threshold": threshold,
        "per_category": category_metrics,
        "micro": prf(micro_counts["tp"], micro_counts["fp"], micro_counts["fn"]),
        "macro": macro,
        "aupr": average_precision(sample_labels, sample_scores),
        "precision_at_80_recall": _precision_at_recall(sample_labels, sample_scores, 0.80),
        "precision_at_90_recall": _precision_at_recall(sample_labels, sample_scores, 0.90),
        "no_answer_accuracy": safe_divide(no_answer_correct, no_answer_total),
        "no_answer_correct": no_answer_correct,
        "no_answer_total": no_answer_total,
    }


def _precision_at_recall(labels: Sequence[bool], scores: Sequence[float], target: float) -> float:
    if not labels or not any(labels):
        return 0.0
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    positives = sum(labels)
    true_positives = 0
    best = 0.0
    for rank, index in enumerate(order, start=1):
        true_positives += labels[index]
        recall = true_positives / positives
        if recall >= target:
            best = max(best, true_positives / rank)
    return best


def _score(answer: Mapping[str, Any]) -> float:
    value = answer.get("score", 1.0)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


__all__ = [
    "DEFAULT_JACCARD_THRESHOLD",
    "evaluate_spans",
    "jaccard_similarity",
    "normalize_text",
    "span_match",
    "token_set",
]
