from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from backend.app.modules.identity.schemas import StrictRequest
from backend.app.modules.reviews.results.schemas import (
    ClauseComparisonResponse,
    ContractClassificationResponse,
    ExtractedFieldResponse,
    RiskFindingResponse,
)


class CompleteReviewRequest(StrictRequest):
    note: str | None = Field(default=None, max_length=2000)


class ContractClassificationRevisionRequest(StrictRequest):
    current_value: Literal["purchase", "sales", "nda", "outsourcing", "employment", "other"]
    status: Literal["confirmed", "corrected", "needs_confirmation"]
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(gt=0)


class ExtractedFieldRevisionRequest(StrictRequest):
    current_value: Any | None
    status: Literal["not_found", "needs_confirmation", "confirmed", "corrected"]
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(gt=0)


class RiskFindingRevisionRequest(StrictRequest):
    status: Literal["pending_review", "confirmed", "false_positive", "processed"]
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    suggestion: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(gt=0)


class ClauseComparisonRevisionRequest(StrictRequest):
    status: Literal["matched", "deviated", "missing", "uncertain"]
    difference_summary: str | None = Field(default=None, max_length=2000)
    suggestion: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(gt=0)


class RevisionedContractClassificationResponse(ContractClassificationResponse):
    revision_id: UUID


class RevisionedExtractedFieldResponse(ExtractedFieldResponse):
    revision_id: UUID


class RevisionedRiskFindingResponse(RiskFindingResponse):
    revision_id: UUID


class RevisionedClauseComparisonResponse(ClauseComparisonResponse):
    revision_id: UUID


__all__ = [
    "ClauseComparisonRevisionRequest",
    "CompleteReviewRequest",
    "ContractClassificationRevisionRequest",
    "ExtractedFieldRevisionRequest",
    "RevisionedClauseComparisonResponse",
    "RevisionedContractClassificationResponse",
    "RevisionedExtractedFieldResponse",
    "RevisionedRiskFindingResponse",
    "RiskFindingRevisionRequest",
]
