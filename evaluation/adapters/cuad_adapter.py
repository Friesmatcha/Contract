"""CUAD SQuAD adapter with validation at the untrusted-data boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

KNOWN_CATEGORIES = (
    "Affiliate License-Licensee",
    "Affiliate License-Licensor",
    "Agreement Date",
    "Anti-Assignment",
    "Audit Rights",
    "Cap On Liability",
    "Change Of Control",
    "Competitive Restriction Exception",
    "Covenant Not To Sue",
    "Document Name",
    "Effective Date",
    "Exclusivity",
    "Expiration Date",
    "Governing Law",
    "Insurance",
    "Ip Ownership Assignment",
    "Irrevocable Or Perpetual License",
    "Joint Ip Ownership",
    "License Grant",
    "Liquidated Damages",
    "Minimum Commitment",
    "Most Favored Nation",
    "No-Solicit Of Customers",
    "No-Solicit Of Employees",
    "Non-Compete",
    "Non-Disparagement",
    "Non-Transferable License",
    "Notice Period To Terminate Renewal",
    "Parties",
    "Post-Termination Services",
    "Price Restrictions",
    "Renewal Term",
    "Revenue/Profit Sharing",
    "Rofr/Rofo/Rofn",
    "Source Code Escrow",
    "Termination For Convenience",
    "Third Party Beneficiary",
    "Uncapped Liability",
    "Unlimited/All-You-Can-Eat-License",
    "Volume Restriction",
    "Warranty Duration",
)


class DatasetValidationError(ValueError):
    """Raised when an archive does not satisfy the expected SQuAD contract."""


def iter_samples(
    path: Path,
    *,
    split: str,
    dataset_id: str = "cuad-v1",
) -> Iterator[dict[str, Any]]:
    """Yield normalized samples without changing official answer content."""
    payload = _load_json(path)
    articles = payload.get("data")
    if not isinstance(articles, list):
        raise DatasetValidationError(f"SQuAD data must be a list: {path.name}")

    seen_questions: set[str] = set()
    seen_documents: set[str] = set()
    for article_index, article in enumerate(articles):
        if not isinstance(article, dict):
            raise DatasetValidationError(f"article {article_index} is not an object")
        document_id = _document_id(article, article_index)
        if document_id in seen_documents:
            raise DatasetValidationError(f"duplicate document_id: {document_id}")
        seen_documents.add(document_id)
        paragraphs = article.get("paragraphs")
        if not isinstance(paragraphs, list):
            raise DatasetValidationError(f"document has no paragraphs: {document_id}")

        for paragraph_index, paragraph in enumerate(paragraphs):
            if not isinstance(paragraph, dict):
                raise DatasetValidationError(f"paragraph {paragraph_index} is not an object")
            context = paragraph.get("context")
            qas = paragraph.get("qas")
            if not isinstance(context, str) or not isinstance(qas, list):
                raise DatasetValidationError(f"invalid paragraph in document: {document_id}")
            for qa_index, qa in enumerate(qas):
                if not isinstance(qa, dict):
                    raise DatasetValidationError(f"question {qa_index} is not an object")
                question_id = _required_string(qa.get("id"), "question id")
                if question_id in seen_questions:
                    raise DatasetValidationError(f"duplicate question_id: {question_id}")
                seen_questions.add(question_id)
                question = _required_string(qa.get("question"), "question")
                impossible = qa.get("is_impossible", False)
                if not isinstance(impossible, bool):
                    raise DatasetValidationError(f"is_impossible is not boolean: {question_id}")
                raw_answers = qa.get("answers", [])
                if not isinstance(raw_answers, list):
                    raise DatasetValidationError(f"answers is not a list: {question_id}")
                if impossible and raw_answers:
                    raise DatasetValidationError(
                        f"impossible question has answers: {question_id}"
                    )
                gold_answers = [
                    _answer(context, answer, question_id) for answer in raw_answers
                ]
                category = _category(qa, question)
                yield {
                    "dataset_id": dataset_id,
                    "split": split,
                    "document_id": document_id,
                    "question_id": question_id,
                    "sample_id": f"{document_id}:{question_id}",
                    "language": "en",
                    "task": "clause_span_extraction",
                    "category": category,
                    "question": question,
                    "context": context,
                    "gold_answers": gold_answers,
                }


def load_samples(path: Path, *, split: str, dataset_id: str = "cuad-v1") -> list[dict[str, Any]]:
    return list(iter_samples(path, split=split, dataset_id=dataset_id))


def validate_split_files(
    split_files: Mapping[str, Path],
    *,
    dataset_id: str = "cuad-v1",
) -> dict[str, Any]:
    """Validate every split and return counts only, never document text."""
    all_questions: set[str] = set()
    all_documents: dict[str, str] = {}
    splits: dict[str, Any] = {}
    for split, path in split_files.items():
        samples = load_samples(path, split=split, dataset_id=dataset_id)
        question_ids = {sample["question_id"] for sample in samples}
        duplicate_questions = all_questions.intersection(question_ids)
        if duplicate_questions:
            raise DatasetValidationError("question_id occurs in multiple split files")
        all_questions.update(question_ids)
        documents = {sample["document_id"] for sample in samples}
        for document_id in documents:
            prior_split = all_documents.get(document_id)
            if prior_split is not None and prior_split != split:
                raise DatasetValidationError(
                    f"document appears in multiple splits: {document_id}"
                )
            all_documents[document_id] = split
        categories = sorted({sample["category"] for sample in samples})
        splits[split] = {
            "samples": len(samples),
            "documents": len(documents),
            "categories": categories,
            "answer_samples": sum(bool(sample["gold_answers"]) for sample in samples),
            "no_answer_samples": sum(not sample["gold_answers"] for sample in samples),
            "gold_answers": sum(len(sample["gold_answers"]) for sample in samples),
            "source_file": path.name,
        }
    return {
        "dataset_id": dataset_id,
        "splits": splits,
        "total_samples": sum(item["samples"] for item in splits.values()),
        "total_documents": len(all_documents),
        "total_questions": len(all_questions),
    }


def select_contracts(samples: Iterable[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return list(samples)
    if limit < 1:
        raise ValueError("limit must be positive")
    selected_documents: list[str] = []
    selected: list[dict[str, Any]] = []
    for sample in samples:
        document_id = sample["document_id"]
        if document_id not in selected_documents:
            if len(selected_documents) >= limit:
                break
            selected_documents.append(document_id)
        selected.append(sample)
    return selected


def write_jsonl(samples: Iterable[dict[str, Any]], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def discover_split_files(extracted_dir: Path) -> dict[str, Path]:
    candidates: dict[str, list[Path]] = {"train": [], "test": [], "validation": []}
    for path in sorted(extracted_dir.rglob("*.json")):
        try:
            payload = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload.get("data"), list):
            continue
        name = path.stem.casefold()
        if "test" in name:
            candidates["test"].append(path)
        elif "train" in name:
            candidates["train"].append(path)
        elif "dev" in name or "valid" in name:
            candidates["validation"].append(path)
    selected: dict[str, Path] = {}
    for split, paths in candidates.items():
        if len(paths) > 1:
            raise DatasetValidationError(f"multiple candidate files for {split}")
        if paths:
            selected[split] = paths[0]
    if not selected:
        raise DatasetValidationError(f"no SQuAD split files found under {extracted_dir.name}")
    return selected


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"invalid JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DatasetValidationError(f"JSON root is not an object: {path.name}")
    return payload


def _document_id(article: dict[str, Any], article_index: int) -> str:
    for key in ("title", "document_id", "contract_id"):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DatasetValidationError(f"article {article_index} has no document id")


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{label} is missing")
    return value


def _category(qa: dict[str, Any], question: str) -> str:
    value = qa.get("category")
    metadata = qa.get("metadata")
    if value is None and isinstance(metadata, dict):
        value = metadata.get("category")
    if isinstance(value, str) and value.strip():
        return value.strip()
    embedded = re.search(r'related to ["\u201c](.*?)["\u201d]', question)
    if embedded:
        return embedded.group(1).strip()
    normalized_question = question.casefold().strip()
    for category in KNOWN_CATEGORIES:
        if normalized_question == category.casefold():
            return category
    return question.strip()


def _answer(context: str, raw_answer: Any, question_id: str) -> dict[str, Any]:
    if not isinstance(raw_answer, dict):
        raise DatasetValidationError(f"answer is not an object: {question_id}")
    text = raw_answer.get("text")
    start = raw_answer.get("answer_start")
    if not isinstance(text, str) or not text:
        raise DatasetValidationError(f"answer text is empty: {question_id}")
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise DatasetValidationError(f"answer offset is invalid: {question_id}")
    end = start + len(text)
    if end > len(context) or context[start:end] != text:
        raise DatasetValidationError(f"answer offset does not match context: {question_id}")
    return {"text": text, "start_offset": start, "end_offset": end}


__all__ = [
    "DatasetValidationError",
    "KNOWN_CATEGORIES",
    "discover_split_files",
    "iter_samples",
    "load_samples",
    "select_contracts",
    "validate_split_files",
    "write_jsonl",
]
