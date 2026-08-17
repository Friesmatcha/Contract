import pytest

from backend.app.modules.identity.service import validate_new_password
from backend.app.shared.errors import ApplicationError


def test_password_policy_requires_at_least_twelve_characters() -> None:
    with pytest.raises(ApplicationError) as exc_info:
        validate_new_password("too-short")

    assert exc_info.value.code == "VALIDATION_ERROR"
    validate_new_password("long-enough-password")
