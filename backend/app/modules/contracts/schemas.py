from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.modules.identity.schemas import StrictRequest

ContractType = Literal["purchase", "sales", "nda", "outsourcing", "employment", "other"]
ContractStatus = Literal["active", "archived"]


class CreateContractRequest(StrictRequest):
    title: str = Field(min_length=1, max_length=500)
    declared_type: ContractType | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized


class UpdateContractRequest(StrictRequest):
    title: str | None = Field(default=None, max_length=500)
    declared_type: ContractType | None = None
    version: int = Field(ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UpdateContractRequest":
        if not self.model_fields_set.intersection({"title", "declared_type"}):
            raise ValueError("at least one field must be updated")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class ContractFileSummary(BaseModel):
    id: UUID
    version_no: int
    is_current: bool
    original_name: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    scan_status: Literal["pending", "clean", "infected", "failed"] | None = None
    storage_status: Literal["quarantine", "stored", "failed"] | None = None
    created_at: datetime | None = None
    external_model_notice_acknowledged_at: datetime | None = None


class FileObjectResponse(BaseModel):
    id: UUID
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str
    scan_status: Literal["pending", "clean", "infected", "failed"]
    storage_status: Literal["quarantine", "stored", "failed"]
    created_at: datetime


class ContractFileUploadResponse(BaseModel):
    file: FileObjectResponse
    contract_file_id: UUID
    version_no: int
    is_current: bool
    external_model_notice_acknowledged_at: datetime


class LatestReviewSummary(BaseModel):
    id: UUID
    status: str


class ContractResponse(BaseModel):
    id: UUID
    display_no: str
    title: str
    declared_type: ContractType | None
    status: ContractStatus
    owner_id: UUID
    current_file: ContractFileSummary | None
    files: list[ContractFileSummary]
    latest_review: LatestReviewSummary | None
    created_at: datetime
    updated_at: datetime
    version: int


class ContractPage(BaseModel):
    items: list[ContractResponse]
    next_cursor: str | None
    has_more: bool


class ContractStatusResponse(BaseModel):
    id: UUID
    status: ContractStatus
    archived_at: datetime | None


class ContractAccessGrantRequest(StrictRequest):
    access_level: Literal["read"]


class ContractAccessGrantResponse(BaseModel):
    contract_id: UUID
    user_id: UUID
    access_level: Literal["read"]
