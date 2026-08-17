from pydantic import BaseModel, Field, field_validator


def _valid_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 320 or "@" not in normalized or normalized.startswith("@"):
        raise ValueError("invalid email")
    return normalized


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


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
