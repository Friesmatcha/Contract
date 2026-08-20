from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ContractType = Literal["purchase", "sales", "nda", "outsourcing", "employment"]
TemplateStatus = Literal["active", "disabled"]
TemplateVersionStatus = Literal["draft", "published"]
ClauseSeverity = Literal["high", "medium", "low"]

NonBlank128 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
NonBlank255 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
NonBlank2000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StandardClauseInput(StrictRequest):
    clause_key: NonBlank128
    name: NonBlank255
    standard_text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=10000),
    ]
    allowed_deviation: Annotated[str, StringConstraints(max_length=2000)]
    severity: ClauseSeverity
    applicability: dict[str, Any]
    suggestion: NonBlank2000
    enabled: bool = True
    order_no: int = Field(gt=0, le=1000)

    @field_validator("applicability")
    @classmethod
    def validate_applicability_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 32:
            raise ValueError("applicability has too many fields")
        return value


class CreateClauseTemplateRequest(StrictRequest):
    name: NonBlank255
    contract_type: ContractType
    business_scenario: str | None = Field(default=None, max_length=128)


class UpdateClauseTemplateRequest(StrictRequest):
    name: NonBlank255 | None = None
    business_scenario: str | None = Field(default=None, max_length=128)
    status: TemplateStatus | None = None
    is_default: bool | None = None
    version: int = Field(gt=0)


class CreateClauseTemplateVersionRequest(StrictRequest):
    change_note: NonBlank2000
    source_version_id: UUID | None = None
    clauses: list[StandardClauseInput] = Field(max_length=200)


class UpdateClauseTemplateVersionRequest(StrictRequest):
    clauses: list[StandardClauseInput] | None = Field(default=None, max_length=200)
    change_note: NonBlank2000 | None = None
    version: int = Field(gt=0)


class PublishClauseTemplateVersionRequest(StrictRequest):
    pass


class StandardClauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clause_key: str
    name: str
    standard_text: str
    allowed_deviation: str
    severity: ClauseSeverity
    applicability: dict[str, Any]
    suggestion: str
    enabled: bool
    order_no: int


class ClauseTemplateVersionSummary(BaseModel):
    organization_id: UUID
    id: UUID
    version_no: int
    status: TemplateVersionStatus
    change_note: str
    effective_at: datetime | None = None
    published_by: UUID | None = None
    clauses: list[StandardClauseResponse] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class ClauseTemplateResponse(BaseModel):
    organization_id: UUID
    id: UUID
    name: str
    contract_type: ContractType
    business_scenario: str
    status: TemplateStatus
    current_published_version_id: UUID | None
    is_default: bool
    version: int


class ClauseTemplateDetailResponse(ClauseTemplateResponse):
    versions: list[ClauseTemplateVersionSummary]


class ClauseTemplateVersionResponse(BaseModel):
    organization_id: UUID
    id: UUID
    template_id: UUID
    version_no: int
    status: TemplateVersionStatus
    change_note: str
    effective_at: datetime | None = None
    published_by: UUID | None = None
    version: int
    is_default: bool
    current_published_version_id: UUID | None
    clauses: list[StandardClauseResponse]


class ClauseTemplateCursorPageResponse(BaseModel):
    items: list[ClauseTemplateResponse]
    next_cursor: str | None
    has_more: bool
