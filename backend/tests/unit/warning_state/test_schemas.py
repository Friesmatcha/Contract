from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.modules.warnings.schemas import WarningEventRequest
from backend.app.modules.warnings.service import _cursor_datetime, _decode_warning_cursor
from backend.app.shared.errors import InvalidCursorError


def test_warning_event_request_normalizes_required_text() -> None:
    request = WarningEventRequest(type="note", note="  需要复核责任范围  ")

    assert request.note == "需要复核责任范围"


def test_warning_event_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WarningEventRequest(type="note", note="说明", unexpected="value")


def test_warning_event_request_accepts_assignment_deadline() -> None:
    deadline = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)

    request = WarningEventRequest(
        type="assign",
        assignee_id="00000000-0000-0000-0000-000000000001",
        due_at=deadline,
    )

    assert request.due_at == deadline


def test_warning_cursor_rejects_corrupt_values_as_contract_validation() -> None:
    with pytest.raises(InvalidCursorError):
        _decode_warning_cursor("not-a-cursor", "triggered_at")
    with pytest.raises(InvalidCursorError):
        _cursor_datetime("not-a-datetime")
