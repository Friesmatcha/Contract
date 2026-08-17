import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import IdempotencyConflictError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    organization_scope,
    platform_scope,
    request_fingerprint,
)
from backend.app.shared.tenant import PlatformContext, TenantContext


def _fingerprint(name: str, operation: str = "POST /api/v1/contracts") -> str:
    return request_fingerprint(method="POST", operation_key=operation, body={"name": name})


def _execute(
    session_factory: sessionmaker[Session],
    *,
    scope: str,
    key: str,
    fingerprint: str,
    callback,
) -> IdempotencyResult:
    from backend.app.shared.idempotency import IdempotencyScope

    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        result = execute_idempotent(
            session,
            scope=IdempotencyScope(scope),
            idempotency_key=key,
            operation_key="POST /api/v1/contracts",
            fingerprint=fingerprint,
            operation=callback,
        )
        unit_of_work.commit()
        return result


def test_same_scope_and_request_replays_but_different_request_conflicts(
    session_factory: sessionmaker[Session],
) -> None:
    context = TenantContext(organization_id=uuid4(), user_id=uuid4(), membership_id=uuid4())
    scope = organization_scope(context)
    resource_id = uuid4()
    calls = 0

    def operation() -> IdempotencyResult:
        nonlocal calls
        calls += 1
        return IdempotencyResult(201, "contract", resource_id)

    first = _execute(
        session_factory,
        scope=scope.value,
        key="shared-key",
        fingerprint=_fingerprint("First"),
        callback=operation,
    )
    replay = _execute(
        session_factory,
        scope=scope.value,
        key="shared-key",
        fingerprint=_fingerprint("First"),
        callback=operation,
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.resource_id == resource_id
    assert calls == 1

    with pytest.raises(IdempotencyConflictError):
        _execute(
            session_factory,
            scope=scope.value,
            key="shared-key",
            fingerprint=_fingerprint("Different"),
            callback=operation,
        )


def test_different_organizations_and_platform_actors_can_reuse_key(
    session_factory: sessionmaker[Session],
) -> None:
    scopes = [
        organization_scope(TenantContext(uuid4(), uuid4(), uuid4())),
        organization_scope(TenantContext(uuid4(), uuid4(), uuid4())),
        platform_scope(PlatformContext(uuid4())),
        platform_scope(PlatformContext(uuid4())),
    ]
    calls = 0

    def operation() -> IdempotencyResult:
        nonlocal calls
        calls += 1
        return IdempotencyResult(201, "resource", uuid4())

    for scope in scopes:
        _execute(
            session_factory,
            scope=scope.value,
            key="reusable-key",
            fingerprint=_fingerprint("Same"),
            callback=operation,
        )

    assert calls == len(scopes)


def test_concurrent_duplicates_execute_operation_once(
    session_factory: sessionmaker[Session],
) -> None:
    scope = platform_scope(PlatformContext(uuid4()))
    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def operation() -> IdempotencyResult:
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=5)
        return IdempotencyResult(201, "organization", uuid4())

    def run() -> IdempotencyResult:
        return _execute(
            session_factory,
            scope=scope.value,
            key="concurrent-key",
            fingerprint=_fingerprint("Concurrent"),
            callback=operation,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(run)
        assert started.wait(timeout=5)
        second_future = executor.submit(run)
        time.sleep(0.2)
        release.set()
        results = [first_future.result(timeout=5), second_future.result(timeout=5)]

    assert calls == 1
    assert sorted(result.replayed for result in results) == [False, True]
