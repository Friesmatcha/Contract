from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ReportFormat = Literal["html", "pdf"]
ReportStatus = Literal["generating", "ready", "failed", "expired"]


class CreateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ReportFormat


class ReportCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    review_task_id: UUID
    format: ReportFormat
    status: ReportStatus


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    display_no: str
    review_task_id: UUID
    format: ReportFormat
    status: ReportStatus
    template_version: str
    created_at: datetime
    generated_at: datetime | None
    expires_at: datetime | None
    download_available: bool
    error_code: str | None


__all__ = ["CreateReportRequest", "ReportCreateResponse", "ReportResponse"]
