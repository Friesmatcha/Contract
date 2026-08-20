from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ResultStatus = Literal["detected", "not_found", "needs_confirmation", "confirmed", "corrected"]
ContractCategory = Literal["purchase", "sales", "nda", "outsourcing", "employment", "other"]
SourceKind = Literal["pdf_page", "image_page", "docx_paragraph", "docx_table_cell"]
CoreFieldKey = Literal[
    "parties",
    "signing_date",
    "contract_amount",
    "performance_period",
    "dispute_resolution",
    "payment_terms",
    "auto_renewal",
]


class ResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceLocatorResponse(ResultResponse):
    source_span_id: UUID
    document_version_id: UUID
    kind: SourceKind
    page_no: int | None
    paragraph_no: int | None
    table_path: str | None
    start_offset: int
    end_offset: int
    bbox: dict[str, float] | None
    quote: str


class ContractClassificationResponse(ResultResponse):
    id: UUID
    model_value: ContractCategory
    current_value: ContractCategory
    confidence: float
    status: ResultStatus
    evidence: list[SourceLocatorResponse]
    version: int


class ExtractedFieldResponse(ResultResponse):
    id: UUID
    field_key: CoreFieldKey
    model_value: Any | None
    current_value: Any | None
    status: ResultStatus
    confidence: float
    evidence: list[SourceLocatorResponse]
    version: int


class ReviewResultsResponse(ResultResponse):
    review_task_id: UUID
    classification: ContractClassificationResponse
    extracted_fields: list[ExtractedFieldResponse]


__all__ = [
    "ContractClassificationResponse",
    "ExtractedFieldResponse",
    "ReviewResultsResponse",
    "SourceLocatorResponse",
]
