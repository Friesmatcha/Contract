from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.modules.contracts.schemas import ContractType
from backend.app.modules.identity.schemas import StrictRequest

FeedbackSubjectType = Literal[
    "classification", "extracted_field", "risk_finding", "clause_comparison"
]
FeedbackLabel = Literal["correct", "incorrect", "modified", "ignored"]


class FeedbackCreateRequest(StrictRequest):
    review_task_id: UUID
    subject_type: FeedbackSubjectType
    subject_id: UUID
    label: FeedbackLabel
    corrected_value: Any | None = None
    note: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_type: FeedbackSubjectType
    subject_id: UUID
    label: FeedbackLabel
    created_by: UUID
    created_at: datetime


class FeedbackSummaryFilters(BaseModel):
    contract_type: ContractType | None = None
    rule_bundle_version_id: UUID | None = None
    model_version: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


class FeedbackCounts(BaseModel):
    correct: int
    incorrect: int
    modified: int
    ignored: int


class FeedbackRiskTypeCount(FeedbackCounts):
    risk_type: str


class FeedbackSummaryResponse(BaseModel):
    filters: FeedbackSummaryFilters
    counts: FeedbackCounts
    by_risk_type: list[FeedbackRiskTypeCount]


__all__ = [
    "FeedbackCreateRequest",
    "FeedbackResponse",
    "FeedbackSummaryFilters",
    "FeedbackSummaryResponse",
]
