from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    user_id: UUID
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class PlatformContext:
    user_id: UUID
