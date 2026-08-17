import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.shared.db import Base, UuidPrimaryKeyMixin
from backend.app.shared.errors import IdempotencyConflictError
from backend.app.shared.tenant import PlatformContext, TenantContext

_SCOPE_PATTERN = re.compile(
    r"^(organization|platform):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY_PARTS = {
    "apikey",
    "authorization",
    "cookie",
    "csrf",
    "password",
    "secret",
    "token",
}


class IdempotencyRecord(UuidPrimaryKeyMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
        CheckConstraint(
            "scope ~ '^(organization|platform):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            "[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="scope_valid",
        ),
        CheckConstraint("char_length(request_fingerprint) = 64", name="fingerprint_valid"),
        CheckConstraint(
            "(response_status IS NULL AND completed_at IS NULL) OR "
            "(response_status BETWEEN 200 AND 299 AND completed_at IS NOT NULL)",
            name="completion_valid",
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
    )

    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None]
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    value: str

    def __post_init__(self) -> None:
        if _SCOPE_PATTERN.fullmatch(self.value) is None:
            raise ValueError("invalid server idempotency scope")


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    response_status: int
    resource_type: str | None
    resource_id: UUID | None
    replayed: bool = False


def organization_scope(context: TenantContext) -> IdempotencyScope:
    return IdempotencyScope(f"organization:{context.organization_id}")


def platform_scope(context: PlatformContext) -> IdempotencyScope:
    return IdempotencyScope(f"platform:{context.user_id}")


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("fingerprint timestamps must include a timezone")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value, key=str):
            string_key = str(key)
            if any(part in _normalized_key(string_key) for part in _SENSITIVE_KEY_PARTS):
                normalized[string_key] = "<excluded>"
            else:
                normalized[string_key] = _canonicalize(value[key])
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_canonicalize(item) for item in value]
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")


def request_fingerprint(
    *,
    method: str,
    operation_key: str,
    path: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "body": _canonicalize(body or {}),
        "method": method.upper(),
        "operation": operation_key,
        "path": _canonicalize(path or {}),
        "query": _canonicalize(query or {}),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def execute_idempotent(
    session: Session,
    *,
    scope: IdempotencyScope,
    idempotency_key: str,
    operation_key: str,
    fingerprint: str,
    operation: Callable[[], IdempotencyResult],
    expires_at: datetime | None = None,
) -> IdempotencyResult:
    if not idempotency_key or len(idempotency_key) > 255:
        raise ValueError("idempotency_key must contain 1 to 255 characters")
    if _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise ValueError("fingerprint must be a SHA-256 hex digest")

    record_id = uuid4()
    inserted_id = session.execute(
        insert(IdempotencyRecord)
        .values(
            id=record_id,
            scope=scope.value,
            operation_key=operation_key,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            created_at=datetime.now(UTC),
            expires_at=expires_at or datetime.now(UTC) + timedelta(hours=24),
        )
        .on_conflict_do_nothing(index_elements=["scope", "idempotency_key"])
        .returning(IdempotencyRecord.id)
    ).scalar_one_or_none()

    if inserted_id is None:
        existing = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope.value,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise RuntimeError("idempotency conflict row disappeared")
        if (
            existing.operation_key != operation_key
            or existing.request_fingerprint != fingerprint
            or existing.response_status is None
        ):
            raise IdempotencyConflictError
        return IdempotencyResult(
            response_status=existing.response_status,
            resource_type=existing.resource_type,
            resource_id=existing.resource_id,
            replayed=True,
        )

    result = operation()
    session.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.id == inserted_id)
        .values(
            response_status=result.response_status,
            resource_type=result.resource_type,
            resource_id=result.resource_id,
            completed_at=datetime.now(UTC),
        )
    )
    return result
