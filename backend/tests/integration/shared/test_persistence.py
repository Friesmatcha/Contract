from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.shared.audit import AuditLog, append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.pagination import paginate_by_created_at
from backend.app.shared.tenant import TenantContext


def _organization(name: str, *, id: UUID | None = None) -> Organization:
    return Organization(id=id or uuid4(), name=name)


def _user(email: str) -> User:
    return User(
        email=email,
        normalized_email=email.strip().lower(),
        display_name=email,
    )


def test_normalized_email_is_globally_unique(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(_user("legal@example.com"))
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(_user("LEGAL@example.com"))
        unit_of_work.commit()


def test_normalized_email_must_be_derived_from_email(
    session_factory: sessionmaker[Session],
) -> None:
    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            User(
                email="legal@example.com",
                normalized_email="different@example.com",
                display_name="Legal",
            )
        )
        unit_of_work.commit()

    organization = _organization("Email Constraint Organization")
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(organization)
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                email="member@example.com",
                normalized_email="different@example.com",
                role="reviewer",
            )
        )
        unit_of_work.commit()


def test_cross_organization_audit_membership_is_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    organization_a = _organization("Organization A")
    organization_b = _organization("Organization B")
    user = _user("reviewer@example.com")
    membership_b = OrganizationMembership(
        organization_id=organization_b.id,
        user_id=user.id,
        email=user.email,
        normalized_email=user.normalized_email,
        display_name=user.display_name,
        role="reviewer",
        status="active",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization_a, organization_b, user, membership_b])
        unit_of_work.commit()

    invalid_context = TenantContext(
        organization_id=organization_a.id,
        user_id=user.id,
        membership_id=membership_b.id,
    )
    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        append_audit_log(
            session,
            actor=invalid_context,
            action="contract.created",
            resource_type="contract",
            request_id="req_cross_tenant",
        )
        unit_of_work.commit()


def test_audit_actor_must_match_membership_user(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _organization("Actor Constraint Organization")
    actor = _user("actor@example.com")
    other_user = _user("other@example.com")
    other_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=other_user.id,
        email=other_user.email,
        normalized_email=other_user.normalized_email,
        role="reviewer",
        status="active",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization, actor, other_user, other_membership])
        unit_of_work.commit()

    invalid_context = TenantContext(
        organization_id=organization.id,
        user_id=actor.id,
        membership_id=other_membership.id,
    )
    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        append_audit_log(
            session,
            actor=invalid_context,
            action="contract.created",
            resource_type="contract",
            request_id="req_wrong_actor",
        )
        unit_of_work.commit()


def test_business_and_audit_changes_roll_back_together(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _organization("Rollback Organization")

    with (
        pytest.raises(RuntimeError, match="force rollback"),
        session_factory() as session,
        UnitOfWork(session),
    ):
        session.add(organization)
        append_audit_log(
            session,
            actor=None,
            organization_id=organization.id,
            action="organization.created",
            resource_type="organization",
            resource_id=organization.id,
            request_id="req_rollback",
        )
        raise RuntimeError("force rollback")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Organization)) == 0
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_audit_logs_are_database_enforced_append_only(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        audit_log = append_audit_log(
            session,
            actor=None,
            action="platform.started",
            resource_type="platform",
            request_id="req_append_only",
        )
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.execute(
            update(AuditLog).where(AuditLog.id == audit_log.id).values(action="changed")
        )
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.execute(delete(AuditLog).where(AuditLog.id == audit_log.id))
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.execute(text("TRUNCATE TABLE audit_logs"))
        unit_of_work.commit()


def test_cursor_pagination_is_stable_for_equal_timestamps(
    session_factory: sessionmaker[Session],
) -> None:
    created_at = datetime(2026, 8, 17, tzinfo=UTC)
    ids = [UUID(int=value) for value in (1, 2, 3)]
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all(
            [
                Organization(
                    id=organization_id,
                    name=f"Organization {organization_id.int}",
                    created_at=created_at,
                )
                for organization_id in ids
            ]
        )
        unit_of_work.commit()

    with session_factory() as session:
        first_page = paginate_by_created_at(
            session,
            select(Organization),
            created_at_column=Organization.created_at,
            id_column=Organization.id,
            limit=2,
        )
        second_page = paginate_by_created_at(
            session,
            select(Organization),
            created_at_column=Organization.created_at,
            id_column=Organization.id,
            limit=2,
            cursor=first_page.next_cursor,
        )

    assert [item.id for item in first_page.items] == [ids[2], ids[1]]
    assert [item.id for item in second_page.items] == [ids[0]]
    assert first_page.has_more is True
    assert second_page.has_more is False
