from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin, VersionMixin


class RiskRuleBundle(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "risk_rule_bundles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_risk_rule_bundles_organization_id_id"),
        UniqueConstraint(
            "organization_id", "normalized_name", name="uq_risk_rule_bundles_organization_name"
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_risk_rule_bundles_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "current_published_version_id"],
            [
                "risk_rule_bundle_versions.organization_id",
                "risk_rule_bundle_versions.bundle_id",
                "risk_rule_bundle_versions.id",
            ],
            name="fk_risk_rule_bundles_current_version_tenant",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint(
            "NOT is_default OR (status = 'active' AND current_published_version_id IS NOT NULL)",
            name="default_available",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "uq_risk_rule_bundles_default",
            "organization_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index(
            "ix_risk_rule_bundles_organization_created_at_id", "organization_id", "created_at", "id"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_published_version_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class RiskRuleBundleVersion(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "risk_rule_bundle_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_risk_rule_bundle_versions_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id", "bundle_id", "version_no", name="uq_risk_rule_bundle_versions_number"
        ),
        UniqueConstraint(
            "organization_id",
            "bundle_id",
            "id",
            name="uq_risk_rule_bundle_versions_organization_bundle_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "bundle_id"],
            ["risk_rule_bundles.organization_id", "risk_rule_bundles.id"],
            name="fk_risk_rule_bundle_versions_bundle_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "published_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_risk_rule_bundle_versions_publisher_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version_no > 0", name="version_no_positive"),
        CheckConstraint("status IN ('draft', 'published')", name="status_valid"),
        CheckConstraint("btrim(change_note) <> ''", name="change_note_not_blank"),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "ix_risk_rule_bundle_versions_organization_bundle_version",
            "organization_id",
            "bundle_id",
            "version_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    bundle_id: Mapped[UUID] = mapped_column(nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default="draft"
    )
    change_note: Mapped[str] = mapped_column(String(2000), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[UUID | None] = mapped_column()


class RiskRule(UuidPrimaryKeyMixin, Base):
    __tablename__ = "risk_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_risk_rules_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "bundle_version_id",
            "rule_key",
            name="uq_risk_rules_bundle_version_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "bundle_version_id"],
            ["risk_rule_bundle_versions.organization_id", "risk_rule_bundle_versions.id"],
            name="fk_risk_rules_version_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("btrim(rule_key) <> ''", name="rule_key_not_blank"),
        CheckConstraint("engine IN ('deterministic', 'model')", name="engine_valid"),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        Index("ix_risk_rules_organization_version", "organization_id", "bundle_version_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    bundle_version_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(128), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    suggestion: Mapped[str] = mapped_column(String(2000), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
