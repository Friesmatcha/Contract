import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import Select, and_, asc, desc, or_
from sqlalchemy.orm import InstrumentedAttribute, Session

from backend.app.shared.errors import ApplicationError, InvalidCursorError, InvalidFilterError

SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class CursorPosition:
    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class CursorPage[T]:
    items: list[T]
    next_cursor: str | None
    has_more: bool


def encode_cursor(position: CursorPosition) -> str:
    if position.created_at.tzinfo is None:
        raise ValueError("cursor timestamps must include a timezone")
    payload = {
        "created_at": position.created_at.isoformat(),
        "id": str(position.id),
        "v": 1,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def decode_cursor(value: str) -> CursorPosition:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding))
        if not isinstance(payload, dict) or set(payload) != {"created_at", "id", "v"}:
            raise ValueError
        if payload["v"] != 1:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        return CursorPosition(created_at=created_at, id=UUID(payload["id"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidCursorError from exc


def validate_filter_fields(filters: dict[str, Any], allowed_fields: set[str]) -> None:
    unknown_fields = sorted(set(filters) - allowed_fields)
    if unknown_fields:
        raise InvalidFilterError(unknown_fields[0])


def paginate_by_created_at[T](
    session: Session,
    statement: Select[tuple[T]],
    *,
    created_at_column: InstrumentedAttribute[datetime],
    id_column: InstrumentedAttribute[UUID],
    limit: int = 20,
    cursor: str | None = None,
    direction: SortDirection = "desc",
) -> CursorPage[T]:
    if not 1 <= limit <= 100:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页数量无效。",
            details={"field": "limit"},
        )

    if cursor is not None:
        position = decode_cursor(cursor)
        if direction == "desc":
            boundary = or_(
                created_at_column < position.created_at,
                and_(created_at_column == position.created_at, id_column < position.id),
            )
        else:
            boundary = or_(
                created_at_column > position.created_at,
                and_(created_at_column == position.created_at, id_column > position.id),
            )
        statement = statement.where(boundary)

    order = desc if direction == "desc" else asc
    rows = session.scalars(
        statement.order_by(order(created_at_column), order(id_column)).limit(limit + 1)
    ).all()
    items = list(cast(list[T], rows[:limit]))
    has_more = len(rows) > limit
    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        next_cursor = encode_cursor(
            CursorPosition(
                created_at=cast(datetime, getattr(last_item, created_at_column.key)),
                id=cast(UUID, getattr(last_item, id_column.key)),
            )
        )
    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
