from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    actor_id: UUID | None
    request_id: str
    before_summary: dict[str, Any] | None
    after_summary: dict[str, Any] | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    next_cursor: str | None
    has_more: bool


__all__ = ["AuditLogPage", "AuditLogResponse"]
