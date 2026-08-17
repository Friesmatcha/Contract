from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.app.shared.errors import InvalidCursorError, InvalidFilterError
from backend.app.shared.pagination import (
    CursorPosition,
    decode_cursor,
    encode_cursor,
    validate_filter_fields,
)


def test_cursor_round_trip() -> None:
    position = CursorPosition(created_at=datetime(2026, 8, 17, tzinfo=UTC), id=uuid4())

    assert decode_cursor(encode_cursor(position)) == position


def test_invalid_cursor_maps_to_validation_error() -> None:
    with pytest.raises(InvalidCursorError) as exc_info:
        decode_cursor("not-a-valid-cursor")

    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {"field": "cursor"}


def test_unknown_filter_is_rejected() -> None:
    with pytest.raises(InvalidFilterError) as exc_info:
        validate_filter_fields({"status": "active", "unknown": "value"}, {"status"})

    assert exc_info.value.details == {"field": "unknown"}
