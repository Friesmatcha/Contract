from uuid import uuid4

import pytest

from backend.app.shared.idempotency import (
    IdempotencyScope,
    organization_scope,
    platform_scope,
    request_fingerprint,
)
from backend.app.shared.tenant import PlatformContext, TenantContext


def test_scopes_are_derived_from_trusted_contexts() -> None:
    organization_id = uuid4()
    user_id = uuid4()

    tenant_scope = organization_scope(
        TenantContext(
            organization_id=organization_id,
            user_id=user_id,
            membership_id=uuid4(),
        )
    )
    actor_scope = platform_scope(PlatformContext(user_id=user_id))

    assert tenant_scope.value == f"organization:{organization_id}"
    assert actor_scope.value == f"platform:{user_id}"


def test_invalid_raw_scope_is_rejected() -> None:
    with pytest.raises(ValueError):
        IdempotencyScope("organization:client-controlled")

    with pytest.raises(ValueError):
        IdempotencyScope("organization:00000000-0000-0000-0000------------")


def test_fingerprint_is_deterministic_and_excludes_secret_values() -> None:
    first = request_fingerprint(
        method="post",
        operation_key="POST /api/v1/platform/organizations",
        query={"b": 2, "a": 1},
        body={
            "name": "Example",
            "credentials": {
                "new_password": "first-password",
                "reset_token": "first-token",
                "client_secret": "first-secret",
            },
        },
    )
    second = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/platform/organizations",
        query={"a": 1, "b": 2},
        body={
            "credentials": {
                "client_secret": "different-secret",
                "reset_token": "different-token",
                "new_password": "different-password",
            },
            "name": "Example",
        },
    )

    assert first == second
    assert "secret" not in first


def test_operation_is_part_of_fingerprint() -> None:
    body = {"name": "Example"}

    create_organization = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/platform/organizations",
        body=body,
    )
    create_contract = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/contracts",
        body=body,
    )

    assert create_organization != create_contract
