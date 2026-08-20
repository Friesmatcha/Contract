"""Add Phase 8A versioned risk rule management.

Revision ID: 20260819_0009
Revises: 20260819_0008
Create Date: 2026-08-19
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0009"
down_revision: str | None = "20260819_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_RULES = (
    (
        "unlimited_liability",
        "unlimited_liability",
        "无限责任或责任范围不封顶",
        "high",
        {"operator": "keyword", "field": "contract_text", "value": "无限责任"},
    ),
    (
        "excessive_liquidated_damages",
        "excessive_liquidated_damages",
        "违约金计算方式不合理",
        "high",
        {"operator": "keyword", "field": "contract_text", "value": "违约金"},
    ),
    (
        "unilateral_termination",
        "unilateral_termination",
        "单方解除或变更权不对等",
        "high",
        {"operator": "keyword", "field": "contract_text", "value": "单方解除"},
    ),
    (
        "unclear_payment",
        "unclear_payment",
        "付款条件不清晰或周期过长",
        "medium",
        {"operator": "field_missing", "field": "payment_terms"},
    ),
    (
        "missing_acceptance",
        "missing_acceptance",
        "验收标准缺失",
        "high",
        {"operator": "field_missing", "field": "acceptance_standard"},
    ),
    (
        "broad_confidentiality",
        "broad_confidentiality",
        "保密义务范围过宽",
        "medium",
        {"operator": "keyword", "field": "contract_text", "value": "永久保密"},
    ),
    (
        "unclear_ip",
        "unclear_ip",
        "知识产权归属不清",
        "high",
        {"operator": "field_missing", "field": "intellectual_property"},
    ),
    (
        "data_compliance",
        "data_compliance",
        "数据合规责任缺失",
        "high",
        {"operator": "field_missing", "field": "data_compliance"},
    ),
    (
        "unfavorable_dispute",
        "unfavorable_dispute",
        "争议解决安排可能不利",
        "medium",
        {"operator": "field_missing", "field": "dispute_resolution"},
    ),
    (
        "auto_renewal",
        "auto_renewal",
        "自动续期或隐性义务",
        "medium",
        {"operator": "keyword", "field": "contract_text", "value": "自动续期"},
    ),
    (
        "force_majeure",
        "force_majeure",
        "不可抗力或迟延履行条款缺失",
        "low",
        {"operator": "field_missing", "field": "force_majeure"},
    ),
)


def _seed_existing_organizations() -> None:
    connection = op.get_bind()
    organization_ids = list(
        connection.execute(sa.text("SELECT id FROM organizations ORDER BY id")).scalars()
    )
    bundle_table = sa.table(
        "risk_rule_bundles",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("normalized_name", sa.String()),
        sa.column("current_published_version_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    version_table = sa.table(
        "risk_rule_bundle_versions",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("bundle_id", sa.Uuid()),
        sa.column("version_no", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("change_note", sa.String()),
        sa.column("effective_at", sa.DateTime(timezone=True)),
    )
    rule_table = sa.table(
        "risk_rules",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("bundle_version_id", sa.Uuid()),
        sa.column("rule_key", sa.String()),
        sa.column("risk_type", sa.String()),
        sa.column("engine", sa.String()),
        sa.column("condition_json", postgresql.JSONB()),
        sa.column("severity", sa.String()),
        sa.column("suggestion", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    audit_table = sa.table(
        "audit_logs",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("action", sa.String()),
        sa.column("resource_type", sa.String()),
        sa.column("resource_id", sa.Uuid()),
        sa.column("request_id", sa.String()),
        sa.column("after_summary_json", postgresql.JSONB()),
    )
    effective_at = datetime.now(UTC)
    for organization_id in organization_ids:
        bundle_id = uuid4()
        version_id = uuid4()
        connection.execute(
            sa.insert(bundle_table),
            {
                "id": bundle_id,
                "organization_id": organization_id,
                "name": "内置风险规则基线",
                "normalized_name": "内置风险规则基线",
                "current_published_version_id": version_id,
                "status": "active",
                "is_default": True,
            },
        )
        connection.execute(
            sa.insert(version_table),
            {
                "id": version_id,
                "organization_id": organization_id,
                "bundle_id": bundle_id,
                "version_no": 1,
                "status": "published",
                "change_note": "系统内置演示基线，不代表具体企业法律意见。",
                "effective_at": effective_at,
            },
        )
        connection.execute(
            sa.insert(rule_table),
            [
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "bundle_version_id": version_id,
                    "rule_key": rule_key,
                    "risk_type": risk_type,
                    "engine": "deterministic",
                    "condition_json": condition,
                    "severity": severity,
                    "suggestion": f"请复核“{title}”相关约定，并结合组织政策确认。",
                    "enabled": True,
                }
                for rule_key, risk_type, title, severity, condition in _BASELINE_RULES
            ],
        )
        connection.execute(
            sa.insert(audit_table),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "action": "risk_rule_version.published",
                "resource_type": "risk_rule_bundle_version",
                "resource_id": version_id,
                "request_id": "phase8a-migration-baseline",
                "after_summary_json": {
                    "bundle_id": str(bundle_id),
                    "status": "published",
                    "is_default": True,
                    "effective_at": effective_at.isoformat(),
                    "source": "system_baseline",
                },
            },
        )


def upgrade() -> None:
    op.create_table(
        "risk_rule_bundles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        sa.CheckConstraint(
            "NOT is_default OR (status = 'active' AND current_published_version_id IS NOT NULL)",
            name="default_available",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_risk_rule_bundles_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_rule_bundles"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_risk_rule_bundles_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "normalized_name", name="uq_risk_rule_bundles_organization_name"
        ),
    )
    op.create_index(
        "uq_risk_rule_bundles_default",
        "risk_rule_bundles",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_risk_rule_bundles_organization_created_at_id",
        "risk_rule_bundles",
        ["organization_id", "created_at", "id"],
    )

    op.create_table(
        "risk_rule_bundle_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("change_note", sa.String(length=2000), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("version_no > 0", name="version_no_positive"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="status_valid"),
        sa.CheckConstraint("btrim(change_note) <> ''", name="change_note_not_blank"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "bundle_id"],
            ["risk_rule_bundles.organization_id", "risk_rule_bundles.id"],
            name="fk_risk_rule_bundle_versions_bundle_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "published_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_risk_rule_bundle_versions_publisher_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_rule_bundle_versions"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_risk_rule_bundle_versions_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "bundle_id", "version_no", name="uq_risk_rule_bundle_versions_number"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "bundle_id",
            "id",
            name="uq_risk_rule_bundle_versions_organization_bundle_id_id",
        ),
    )
    op.create_index(
        "ix_risk_rule_bundle_versions_organization_bundle_version",
        "risk_rule_bundle_versions",
        ["organization_id", "bundle_id", "version_no"],
    )

    op.create_table(
        "risk_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bundle_version_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("risk_type", sa.String(length=128), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("condition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("suggestion", sa.String(length=2000), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(rule_key) <> ''", name="rule_key_not_blank"),
        sa.CheckConstraint("engine IN ('deterministic', 'model')", name="engine_valid"),
        sa.CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        sa.ForeignKeyConstraint(
            ["organization_id", "bundle_version_id"],
            ["risk_rule_bundle_versions.organization_id", "risk_rule_bundle_versions.id"],
            name="fk_risk_rules_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_rules"),
        sa.UniqueConstraint("organization_id", "id", name="uq_risk_rules_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id",
            "bundle_version_id",
            "rule_key",
            name="uq_risk_rules_bundle_version_key",
        ),
    )
    op.create_index(
        "ix_risk_rules_organization_version", "risk_rules", ["organization_id", "bundle_version_id"]
    )
    _seed_existing_organizations()
    op.create_foreign_key(
        "fk_risk_rule_bundles_current_version_tenant",
        "risk_rule_bundles",
        "risk_rule_bundle_versions",
        ["organization_id", "id", "current_published_version_id"],
        ["organization_id", "bundle_id", "id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION enforce_risk_rule_bundle_current_version_published() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.current_published_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                FROM risk_rule_bundle_versions
                WHERE organization_id = NEW.organization_id
                  AND bundle_id = NEW.id
                  AND id = NEW.current_published_version_id
                  AND status = 'published'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'ck_risk_rule_bundles_current_version_published',
                    MESSAGE = 'current risk rule bundle version must be published';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER risk_rule_bundles_current_version_published
        AFTER INSERT OR UPDATE ON risk_rule_bundles
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_risk_rule_bundle_current_version_published()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_published_risk_rule_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'published risk rule versions are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_rule_bundle_versions_immutable
        BEFORE UPDATE OR DELETE ON risk_rule_bundle_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_published_risk_rule_version_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_published_risk_rule_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            source_status varchar(32);
            target_status varchar(32);
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT status INTO source_status
                FROM risk_rule_bundle_versions
                WHERE organization_id = OLD.organization_id
                  AND id = OLD.bundle_version_id;

                IF source_status = 'published' THEN
                    RAISE EXCEPTION 'rules in published risk rule versions are immutable';
                END IF;
            END IF;

            IF TG_OP <> 'DELETE' THEN
                SELECT status INTO target_status
                FROM risk_rule_bundle_versions
                WHERE organization_id = NEW.organization_id
                  AND id = NEW.bundle_version_id;

                IF target_status = 'published' THEN
                    RAISE EXCEPTION 'rules in published risk rule versions are immutable';
                END IF;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_rules_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON risk_rules
        FOR EACH ROW EXECUTE FUNCTION prevent_published_risk_rule_mutation()
        """
    )


def downgrade() -> None:
    # Migration-owned seed rows are the only audit records removed on downgrade.
    op.execute("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only")
    op.execute(
        """
        DELETE FROM audit_logs
        WHERE request_id = 'phase8a-migration-baseline'
          AND action = 'risk_rule_version.published'
          AND resource_type = 'risk_rule_bundle_version'
           AND after_summary_json ->> 'source' = 'system_baseline'
        """
    )
    op.execute("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_append_only")
    op.execute(
        "DROP TRIGGER IF EXISTS risk_rule_bundles_current_version_published "
        "ON risk_rule_bundles"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_risk_rule_bundle_current_version_published()")
    op.execute("DROP TRIGGER IF EXISTS risk_rules_immutable ON risk_rules")
    op.execute("DROP FUNCTION IF EXISTS prevent_published_risk_rule_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS risk_rule_bundle_versions_immutable "
        "ON risk_rule_bundle_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_published_risk_rule_version_mutation()")
    op.drop_constraint(
        "fk_risk_rule_bundles_current_version_tenant", "risk_rule_bundles", type_="foreignkey"
    )
    op.drop_index("ix_risk_rules_organization_version", table_name="risk_rules")
    op.drop_table("risk_rules")
    op.drop_index(
        "ix_risk_rule_bundle_versions_organization_bundle_version",
        table_name="risk_rule_bundle_versions",
    )
    op.drop_table("risk_rule_bundle_versions")
    op.drop_index("ix_risk_rule_bundles_organization_created_at_id", table_name="risk_rule_bundles")
    op.drop_index("uq_risk_rule_bundles_default", table_name="risk_rule_bundles")
    op.drop_table("risk_rule_bundles")
