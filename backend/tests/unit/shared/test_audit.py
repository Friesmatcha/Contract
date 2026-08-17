from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from backend.app.shared.audit import append_audit_log


def test_audit_summary_rejects_sensitive_fields() -> None:
    session = Mock(spec=Session)

    with pytest.raises(ValueError, match="sensitive"):
        append_audit_log(
            session,
            actor=None,
            action="configuration.changed",
            resource_type="configuration",
            request_id="req_test",
            after={"settings": {"apiKey": "must-not-be-stored"}},
        )

    session.add.assert_not_called()
