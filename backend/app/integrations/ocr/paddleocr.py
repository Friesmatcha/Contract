import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from numbers import Real
from typing import Any, Protocol

from PIL import Image


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    bbox: dict[str, float]


class OcrEngine(Protocol):
    def recognize(self, image: bytes) -> list[OcrLine]: ...


class PaddleOcrEngine:
    """Lazy PaddleOCR adapter so text-only documents do not load OCR models."""

    def __init__(self, *, lang: str = "ch") -> None:
        self.lang = lang
        self._engine: Any | None = None

    def _load(self) -> Any:
        if self._engine is None:
            cache_home = os.environ.get(
                "PADDLE_PDX_CACHE_HOME",
                os.path.join(tempfile.gettempdir(), "contract-review", "paddlex"),
            )
            os.makedirs(cache_home, exist_ok=True)
            os.environ["PADDLE_PDX_CACHE_HOME"] = cache_home
            previous_home = os.environ.get("HOME")
            previous_userprofile = os.environ.get("USERPROFILE")
            os.environ["HOME"] = cache_home
            os.environ["USERPROFILE"] = cache_home
            try:
                from paddleocr import PaddleOCR

                self._engine = PaddleOCR(
                    lang=self.lang,
                    device="cpu",
                    enable_mkldnn=False,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            finally:
                if previous_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = previous_home
                if previous_userprofile is None:
                    os.environ.pop("USERPROFILE", None)
                else:
                    os.environ["USERPROFILE"] = previous_userprofile
        return self._engine

    def recognize(self, image: bytes) -> list[OcrLine]:
        from numpy import asarray

        with Image.open(BytesIO(image)) as opened:
            array = asarray(opened.convert("RGB"))
        engine = self._load()
        if hasattr(engine, "predict"):
            return _parse_predict_results(engine.predict(array))
        return _parse_legacy_results(engine.ocr(array, cls=True))


def _parse_predict_results(results: Any) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for result in results or []:
        payload = getattr(result, "json", result)
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            continue
        payload = payload.get("res", payload)
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes", payload.get("dt_polys", []))
        for text, score, box in zip(texts, scores, boxes, strict=False):
            normalized = str(text).strip()
            if normalized:
                lines.append(
                    OcrLine(
                        text=normalized,
                        confidence=max(0.0, min(1.0, float(score))),
                        bbox=_bbox_from_points(box),
                    )
                )
    return lines


def _parse_legacy_results(results: Any) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for page in results or []:
        for item in page or []:
            if len(item) != 2:
                continue
            points, recognized = item
            text, score = recognized
            normalized = str(text).strip()
            if normalized:
                lines.append(
                    OcrLine(
                        text=normalized,
                        confidence=max(0.0, min(1.0, float(score))),
                        bbox=_bbox_from_points(points),
                    )
                )
    return lines


def _bbox_from_points(points: Any) -> dict[str, float]:
    if hasattr(points, "tolist"):
        points = points.tolist()
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or not points:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    if len(points) == 4 and all(isinstance(value, Real) for value in points):
        left, top, right, bottom = (float(value) for value in points)
        return {
            "x": left,
            "y": top,
            "width": max(0.0, right - left),
            "height": max(0.0, bottom - top),
        }
    coordinates: list[tuple[float, float]] = []
    for point in points:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2:
            coordinates.append((float(point[0]), float(point[1])))
    if not coordinates:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    left = min(point[0] for point in coordinates)
    top = min(point[1] for point in coordinates)
    right = max(point[0] for point in coordinates)
    bottom = max(point[1] for point in coordinates)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}
