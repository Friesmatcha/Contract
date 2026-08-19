from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin, VersionMixin


class Contract(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_contracts_organization_id_id"),
        UniqueConstraint("display_no", name="uq_contracts_display_no"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_contracts_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contracts_owner_membership_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("btrim(title) <> ''", name="title_not_blank"),
        CheckConstraint(
            "declared_type IS NULL OR declared_type IN "
            "('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="declared_type_valid",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "ix_contracts_organization_created_at_id",
            "organization_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_contracts_organization_status_created_at_id",
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
        Index("ix_contracts_organization_owner_id", "organization_id", "owner_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    display_no: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    declared_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    owner_id: Mapped[UUID] = mapped_column(nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContractAccessGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_contract_access_grants_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "contract_id",
            "user_id",
            name="uq_contract_access_grants_contract_user",
        ),
        ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_contract_access_grants_contract_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contract_access_grants_user_membership_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("access_level IN ('read')", name="access_level_valid"),
        Index(
            "ix_contract_access_grants_organization_contract_user",
            "organization_id",
            "contract_id",
            "user_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    access_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="read", server_default="read"
    )
