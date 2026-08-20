from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin, VersionMixin


class ClauseTemplate(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "clause_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_clause_templates_organization_id_id"),
        UniqueConstraint(
            "organization_id", "normalized_name", name="uq_clause_templates_organization_name"
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clause_templates_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "current_published_version_id"],
            [
                "clause_template_versions.organization_id",
                "clause_template_versions.template_id",
                "clause_template_versions.id",
            ],
            name="fk_clause_templates_current_version_tenant",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "contract_type IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment')",
            name="contract_type_valid",
        ),
        CheckConstraint(
            "business_scenario = lower(btrim(business_scenario)) "
            "AND btrim(business_scenario) <> ''",
            name="business_scenario_canonical",
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint(
            "NOT is_default OR (status = 'active' AND current_published_version_id IS NOT NULL)",
            name="default_available",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "uq_clause_templates_default",
            "organization_id",
            "contract_type",
            "business_scenario",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index(
            "ix_clause_templates_organization_scope_created",
            "organization_id",
            "contract_type",
            "business_scenario",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(32), nullable=False)
    business_scenario: Mapped[str] = mapped_column(String(128), nullable=False)
    current_published_version_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class ClauseTemplateVersion(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "clause_template_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_clause_template_versions_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "template_id",
            "version_no",
            name="uq_clause_template_versions_number",
        ),
        UniqueConstraint(
            "organization_id",
            "template_id",
            "id",
            name="uq_clause_template_versions_organization_template_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["clause_templates.organization_id", "clause_templates.id"],
            name="fk_clause_template_versions_template_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "published_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_clause_template_versions_publisher_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version_no > 0", name="version_no_positive"),
        CheckConstraint("status IN ('draft', 'published')", name="status_valid"),
        CheckConstraint("btrim(change_note) <> ''", name="change_note_not_blank"),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "ix_clause_template_versions_organization_template_version",
            "organization_id",
            "template_id",
            "version_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    template_id: Mapped[UUID] = mapped_column(nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default="draft"
    )
    change_note: Mapped[str] = mapped_column(String(2000), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[UUID | None] = mapped_column()


class StandardClause(UuidPrimaryKeyMixin, Base):
    __tablename__ = "standard_clauses"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_standard_clauses_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "template_version_id",
            "clause_key",
            name="uq_standard_clauses_version_key",
        ),
        UniqueConstraint(
            "organization_id",
            "template_version_id",
            "order_no",
            name="uq_standard_clauses_version_order",
        ),
        ForeignKeyConstraint(
            ["organization_id", "template_version_id"],
            ["clause_template_versions.organization_id", "clause_template_versions.id"],
            name="fk_standard_clauses_version_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("btrim(clause_key) <> ''", name="clause_key_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("btrim(standard_text) <> ''", name="standard_text_not_blank"),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        CheckConstraint("btrim(suggestion) <> ''", name="suggestion_not_blank"),
        CheckConstraint("order_no > 0", name="order_no_positive"),
        Index(
            "ix_standard_clauses_organization_version_order",
            "organization_id",
            "template_version_id",
            "order_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    template_version_id: Mapped[UUID] = mapped_column(nullable=False)
    clause_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_text: Mapped[str] = mapped_column(String(10000), nullable=False)
    allowed_deviation: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    applicability_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    suggestion: Mapped[str] = mapped_column(String(2000), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
