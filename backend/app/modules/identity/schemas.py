from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _valid_email(value: str) -> str:
    normalized = _normalize_email(value)
    if len(normalized) > 320 or "@" not in normalized or normalized.startswith("@"):
        raise ValueError("invalid email")
    return normalized


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _normalize_email = field_validator("email")(_normalize_email)


class PasswordResetRequest(BaseModel):
    email: str

    _normalize_email = field_validator("email")(_valid_email)


class PasswordResetConfirmation(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=128)


class InvitationAcceptance(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=128)


class SessionUser(BaseModel):
    id: str
    email: str
    display_name: str
    status: str
    is_platform_admin: bool


class SessionMembership(BaseModel):
    organization_id: str
    organization_name: str
    role: str
    status: str


class SessionResponse(BaseModel):
    user: SessionUser
    memberships: list[SessionMembership]
    csrf_token: str


class LoginOrganization(BaseModel):
    id: str
    name: str
    role: str


class LoginResponse(BaseModel):
    user: SessionUser
    organizations: list[LoginOrganization]
    csrf_token: str


class PasswordResetAccepted(BaseModel):
    accepted: bool
    message: str


class InvitationAcceptanceResponse(BaseModel):
    user_id: str
    organization_id: str
    role: str
    status: str


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateOrganizationRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=255)
    initial_admin_email: str = Field(min_length=3, max_length=320)
    retention_days: int = Field(default=180, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("organization name is required")
        return normalized

    _normalize_initial_admin_email = field_validator("initial_admin_email")(_valid_email)


class UpdateOrganizationRequest(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["active", "disabled"] | None = None
    retention_days: int | None = Field(default=None, ge=0)
    version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("organization name is required")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UpdateOrganizationRequest":
        if self.name is None and self.status is None and self.retention_days is None:
            raise ValueError("at least one field must be updated")
        return self


class PlatformOrganizationListItem(BaseModel):
    id: str
    name: str
    status: Literal["active", "disabled"]
    retention_days: int
    created_at: datetime


class PlatformOrganizationPage(BaseModel):
    items: list[PlatformOrganizationListItem]
    next_cursor: str | None
    has_more: bool


class OrganizationResponse(BaseModel):
    id: str
    name: str
    status: Literal["active", "disabled"]
    retention_days: int
    settings: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class OrganizationProfileResponse(BaseModel):
    id: str
    name: str
    status: Literal["active", "disabled"]
    my_role: Literal["org_admin", "reviewer", "viewer"]
    permissions: list[str]


class OrganizationSettingsResponse(BaseModel):
    file_size_limit_bytes: int
    page_limit: int
    concurrent_review_limit: int
    warn_on_medium_risk: bool
    ocr_low_confidence_threshold: float
    retention_days: int
    report_watermark: str
    version: int


class UpdateOrganizationSettingsRequest(StrictRequest):
    file_size_limit_bytes: int | None = Field(default=None, ge=1)
    page_limit: int | None = Field(default=None, ge=1)
    concurrent_review_limit: int | None = Field(default=None, ge=1)
    warn_on_medium_risk: bool | None = None
    ocr_low_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    retention_days: int | None = Field(default=None, ge=0)
    report_watermark: str | None = Field(default=None, max_length=255)
    version: int = Field(ge=1)

    @field_validator("report_watermark")
    @classmethod
    def normalize_watermark(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_update(self) -> "UpdateOrganizationSettingsRequest":
        fields = (
            self.file_size_limit_bytes,
            self.page_limit,
            self.concurrent_review_limit,
            self.warn_on_medium_risk,
            self.ocr_low_confidence_threshold,
            self.retention_days,
            self.report_watermark,
        )
        if all(value is None for value in fields):
            raise ValueError("at least one field must be updated")
        return self


class ModelConfigurationResponse(BaseModel):
    provider: str
    model: str
    model_source: Literal["environment"]
    timeout_seconds: int
    max_retries: int
    hard_budget_enabled: Literal[False]
    usage_tracking_enabled: bool
    organization_overrides_allowed: Literal[False]
    secret_configured: bool
    status: Literal["active", "disabled"]
    version: int


class UpdateModelConfigurationRequest(StrictRequest):
    timeout_seconds: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    usage_tracking_enabled: bool | None = None
    status: Literal["active", "disabled"] | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_update(self) -> "UpdateModelConfigurationRequest":
        if (
            self.timeout_seconds is None
            and self.max_retries is None
            and self.usage_tracking_enabled is None
            and self.status is None
        ):
            raise ValueError("at least one field must be updated")
        return self
