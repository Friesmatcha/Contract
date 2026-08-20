from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.modules.contracts.schemas import ContractType

WarningStatus = Literal["pending_confirmation", "in_progress", "ignored", "resolved", "closed"]
WarningSeverity = Literal["high", "medium", "low"]
WarningEventType = Literal[
    "confirm", "false_positive", "ignore", "assign", "note", "resolve", "close", "reopen"
]
NotificationStatus = Literal["unread", "read"]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WarningEventRequest(StrictRequest):
    type: WarningEventType
    note: str | None = Field(default=None, max_length=2000)
    assignee_id: UUID | None = None
    due_at: datetime | None = None
    resolution: str | None = Field(default=None, max_length=5000)
    revision_id: UUID | None = None

    @field_validator("note", "resolution")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class WarningListQuery(StrictRequest):
    status: WarningStatus | None = None
    severity: WarningSeverity | None = None
    contract_type: ContractType | None = None
    assignee_id: UUID | None = None
    risk_type: str | None = Field(default=None, max_length=128)
    triggered_from: datetime | None = None
    triggered_to: datetime | None = None
    sort: Literal["triggered_at", "priority", "due_at"] = "triggered_at"
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class WarningEventResponse(BaseModel):
    event_id: UUID
    event_type: str
    from_status: WarningStatus | None
    to_status: WarningStatus | None
    actor_id: UUID | None
    note: str | None = None
    assignee_id: UUID | None = None
    due_at: datetime | None = None
    created_at: datetime


class WarningEvidenceResponse(BaseModel):
    source_span_id: UUID
    document_version_id: UUID
    kind: str
    page_no: int | None
    paragraph_no: int | None
    table_path: str | None
    start_offset: int
    end_offset: int
    bbox: dict[str, float] | None
    quote: str


class WarningAssigneeResponse(BaseModel):
    id: UUID
    display_name: str | None
    email: str


class WarningListItem(BaseModel):
    id: UUID
    contract_id: UUID
    review_task_id: UUID
    severity: WarningSeverity
    status: WarningStatus
    priority: WarningSeverity
    assignee_id: UUID | None
    due_at: datetime | None
    trigger_type: str
    triggered_at: datetime


class WarningSummary(BaseModel):
    unprocessed_count: int
    high_count: int


class WarningPage(BaseModel):
    items: list[WarningListItem]
    next_cursor: str | None
    has_more: bool
    summary: WarningSummary


class WarningDetailResponse(BaseModel):
    id: UUID
    contract_id: UUID
    review_task_id: UUID
    trigger_type: str
    triggered_at: datetime
    severity: WarningSeverity
    priority: WarningSeverity
    status: WarningStatus
    risk_finding_id: UUID | None
    clause_comparison_id: UUID | None
    extracted_field_id: UUID | None
    classification_id: UUID | None
    assignee: WarningAssigneeResponse | None
    assignee_id: UUID | None
    due_at: datetime | None
    resolution: str | None
    revision_id: UUID | None
    closed_at: datetime | None
    evidence: list[WarningEvidenceResponse]
    events: list[WarningEventResponse]


class NotificationListQuery(StrictRequest):
    status: NotificationStatus | None = None
    warning_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class NotificationListItem(BaseModel):
    id: UUID
    warning_id: UUID
    channel: Literal["in_app"]
    status: NotificationStatus
    title: str
    body: str
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationListItem]
    next_cursor: str | None
    has_more: bool


class NotificationReadResponse(BaseModel):
    id: UUID
    status: Literal["read"]
    read_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


__all__ = [
    "NotificationListQuery",
    "NotificationPage",
    "NotificationReadResponse",
    "UnreadCountResponse",
    "WarningDetailResponse",
    "WarningEventRequest",
    "WarningEventResponse",
    "WarningListQuery",
    "WarningPage",
]
