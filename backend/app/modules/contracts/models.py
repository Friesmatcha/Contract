from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
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


class FileObject(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_objects"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_file_objects_organization_id_id"),
        UniqueConstraint("storage_key", name="uq_file_objects_storage_key"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_file_objects_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="sha256_hex",
        ),
        CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'failed')",
            name="scan_status_valid",
        ),
        CheckConstraint(
            "storage_status IN ('quarantine', 'stored', 'deleting', 'deleted', 'failed')",
            name="storage_status_valid",
        ),
        Index("ix_file_objects_organization_sha256", "organization_id", "sha256"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_status: Mapped[str] = mapped_column(String(32), nullable=False)


class ContractFile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_files"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_contract_files_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "contract_id",
            "version_no",
            name="uq_contract_files_contract_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_contract_files_contract_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_contract_files_file_object_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "external_model_notice_acknowledged_by"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_contract_files_notice_actor_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version_no > 0", name="version_no_positive"),
        Index(
            "uq_contract_files_current",
            "organization_id",
            "contract_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            "ix_contract_files_organization_contract_version",
            "organization_id",
            "contract_id",
            "version_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_id: Mapped[UUID] = mapped_column(nullable=False)
    file_object_id: Mapped[UUID] = mapped_column(nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    external_model_notice_acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    external_model_notice_acknowledged_by: Mapped[UUID] = mapped_column(nullable=False)
