from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

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
Comparison = Literal["gt", "gte", "lt", "lte", "eq"]
TextRuleField = Literal["contract_text"]
AmountRuleField = Literal["contract_amount"]
DateRuleField = Literal["signing_date"]
PresenceRuleField = Literal[
    "parties",
    "signing_date",
    "contract_amount",
    "performance_period",
    "dispute_resolution",
    "payment_terms",
    "auto_renewal",
    "acceptance_standard",
    "intellectual_property",
    "data_compliance",
    "force_majeure",
]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Condition(StrictRequest):
    pass


class KeywordCondition(_Condition):
    operator: Literal["keyword"]
    field: TextRuleField
    value: NonBlank2000


class RegexCondition(_Condition):
    operator: Literal["regex"]
    field: TextRuleField
    pattern: str = Field(min_length=1, max_length=1000)

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError("must be a valid regular expression") from exc
        return value


class AmountThresholdCondition(_Condition):
    operator: Literal["amount_threshold"]
    field: AmountRuleField
    comparison: Comparison
    value: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("value")
    @classmethod
    def validate_decimal(cls, value: str) -> str:
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value):
            raise ValueError("must be a decimal string")
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("must be a decimal string") from exc
        if not parsed.is_finite():
            raise ValueError("must be a finite decimal string")
        return value


class DateThresholdCondition(_Condition):
    operator: Literal["date_threshold"]
    field: DateRuleField
    comparison: Comparison
    value: str = Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("value")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be a valid YYYY-MM-DD date") from exc
        return value


class FieldExistsCondition(_Condition):
    operator: Literal["field_exists"]
    field: PresenceRuleField


class FieldMissingCondition(_Condition):
    operator: Literal["field_missing"]
    field: PresenceRuleField


class SemanticCondition(_Condition):
    operator: Literal["semantic"]


class AllCondition(_Condition):
    operator: Literal["all"]
    conditions: list[RiskRuleCondition] = Field(min_length=1, max_length=20)


class AnyCondition(_Condition):
    operator: Literal["any"]
    conditions: list[RiskRuleCondition] = Field(min_length=1, max_length=20)


class NotCondition(_Condition):
    operator: Literal["not"]
    condition: RiskRuleCondition


type RiskRuleCondition = Annotated[
    KeywordCondition
    | RegexCondition
    | AmountThresholdCondition
    | DateThresholdCondition
    | FieldExistsCondition
    | FieldMissingCondition
    | SemanticCondition
    | AllCondition
    | AnyCondition
    | NotCondition,
    Field(discriminator="operator"),
]

for recursive_model in (AllCondition, AnyCondition, NotCondition):
    recursive_model.model_rebuild(
        _types_namespace={"RiskRuleCondition": RiskRuleCondition},
    )


class RiskRuleInput(StrictRequest):
    rule_key: NonBlank128
    risk_type: NonBlank128
    engine: Literal["deterministic", "model"]
    condition: RiskRuleCondition
    severity: Literal["high", "medium", "low"]
    suggestion: NonBlank2000
    enabled: bool = True


class CreateRiskRuleBundleRequest(StrictRequest):
    name: NonBlank255


class UpdateRiskRuleBundleRequest(StrictRequest):
    name: NonBlank255 | None = None
    status: Literal["active", "disabled"] | None = None
    is_default: bool | None = None
    version: int = Field(gt=0)


class CreateRiskRuleVersionRequest(StrictRequest):
    change_note: NonBlank2000
    source_version_id: UUID | None = None
    rules: list[RiskRuleInput] = Field(min_length=1, max_length=200)


class UpdateRiskRuleVersionRequest(StrictRequest):
    rules: list[RiskRuleInput] | None = Field(default=None, min_length=1, max_length=200)
    change_note: NonBlank2000 | None = None
    version: int = Field(gt=0)


class PublishRiskRuleVersionRequest(StrictRequest):
    pass


class RiskRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_key: str
    risk_type: str
    engine: Literal["deterministic", "model"]
    condition: RiskRuleCondition
    severity: Literal["high", "medium", "low"]
    suggestion: str
    enabled: bool


class RiskRuleVersionSummary(BaseModel):
    organization_id: UUID
    id: UUID
    version_no: int
    status: Literal["draft", "published"]
    change_note: str
    effective_at: datetime | None = None
    published_by: UUID | None = None
    rule_count: int
    rules: list[RiskRuleResponse] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class RiskRuleBundleResponse(BaseModel):
    organization_id: UUID
    id: UUID
    name: str
    status: Literal["active", "disabled"]
    current_published_version_id: UUID | None
    is_default: bool
    version: int


class RiskRuleBundleDetailResponse(RiskRuleBundleResponse):
    versions: list[RiskRuleVersionSummary]


class RiskRuleVersionResponse(BaseModel):
    organization_id: UUID
    id: UUID
    bundle_id: UUID
    version_no: int
    status: Literal["draft", "published"]
    change_note: str
    effective_at: datetime | None = None
    published_by: UUID | None = None
    version: int
    is_default: bool
    current_published_version_id: UUID | None = None
    rules: list[RiskRuleResponse]


class CursorPageResponse(BaseModel):
    items: list[RiskRuleBundleResponse]
    next_cursor: str | None
    has_more: bool
