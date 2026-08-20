from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ResultStatus = Literal["detected", "not_found", "needs_confirmation", "confirmed", "corrected"]
RiskFindingStatus = Literal["pending_review", "confirmed", "false_positive", "processed"]
RiskFindingSource = Literal["rule", "model"]
ClauseComparisonStatus = Literal["matched", "deviated", "missing", "uncertain"]
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


class RiskFindingResponse(ResultResponse):
    id: UUID
    risk_type: str
    severity: Literal["high", "medium", "low"]
    title: str
    description: str
    basis: str
    suggestion: str
    confidence: float
    source: RiskFindingSource
    status: RiskFindingStatus
    evidence: list[SourceLocatorResponse]
    version: int


class ClauseComparisonResponse(ResultResponse):
    id: UUID
    clause_key: str
    status: ClauseComparisonStatus
    contract_text: str | None
    difference_summary: str | None
    severity: Literal["high", "medium", "low"]
    suggestion: str
    evidence: list[SourceLocatorResponse]
    version: int


class ReviewResultsSummary(ResultResponse):
    risk_total: int
    high: int
    medium: int
    low: int
    warning_total: int
    unresolved_count: int


class ReviewResultsResponse(ResultResponse):
    review_task_id: UUID
    classification: ContractClassificationResponse
    extracted_fields: list[ExtractedFieldResponse]
    risk_findings: list[RiskFindingResponse]
    clause_comparisons: list[ClauseComparisonResponse]
    summary: ReviewResultsSummary


__all__ = [
    "ContractClassificationResponse",
    "ExtractedFieldResponse",
    "RiskFindingResponse",
    "ClauseComparisonResponse",
    "ReviewResultsSummary",
    "ReviewResultsResponse",
    "SourceLocatorResponse",
]
