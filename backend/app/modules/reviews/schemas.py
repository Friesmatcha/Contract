from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.modules.identity.schemas import StrictRequest

ReviewStatus = Literal[
    "pending",
    "parsing",
    "reviewing",
    "pending_review",
    "completed",
    "failed",
    "archived",
]
ReviewStage = Literal[
    "parsing",
    "classification",
    "extraction",
    "risk_analysis",
    "clause_comparison",
    "report",
]
ReviewStageStatus = Literal["pending", "running", "succeeded", "failed", "retryable"]


class CreateReviewTaskRequest(StrictRequest):
    contract_file_id: UUID
    document_version_id: UUID | None = None
    rule_bundle_version_id: UUID | None = None
    clause_template_version_id: UUID | None = None
    business_scenario: str = Field(default="standard", min_length=1, max_length=128)

    @field_validator("business_scenario")
    @classmethod
    def normalize_business_scenario(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            return "standard"
        return normalized


class RetryReviewTaskRequest(StrictRequest):
    from_stage: ReviewStage | None = None


class ReviewStageRunResponse(BaseModel):
    id: UUID
    stage: ReviewStage
    status: ReviewStageStatus
    attempt_no: int
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReviewTaskResponse(StrictRequest):
    id: UUID
    display_no: str
    contract_id: UUID
    contract_file_id: UUID
    document_version_id: UUID | None
    status: ReviewStatus
    progress: int = Field(ge=0, le=100)
    current_stage: str
    rule_bundle_version_id: UUID
    clause_template_version_id: UUID
    business_scenario: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    completed_by: UUID | None = None
    completed_at: datetime | None = None
    stage_runs: list[ReviewStageRunResponse] | None = None


class RetryReviewTaskResponse(StrictRequest):
    review_task_id: UUID
    status: Literal["pending"]
    resumed_from_stage: ReviewStage
