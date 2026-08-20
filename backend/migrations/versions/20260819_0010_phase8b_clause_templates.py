"""Add Phase 8B versioned clause template management.

Revision ID: 20260819_0010
Revises: 20260819_0009
Create Date: 2026-08-20
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0010"
down_revision: str | None = "20260819_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_TEMPLATES = (
    ("purchase", "采购合同演示基线"),
    ("sales", "销售合同演示基线"),
    ("nda", "保密协议演示基线"),
    ("outsourcing", "服务外包合同演示基线"),
    ("employment", "劳动合同演示基线"),
)

_BASELINE_CLAUSES = (
    (
        "payment",
        "付款",
        "付款节点、期限和支付条件应当明确，并与验收或交付安排保持一致。",
        "付款期限和节点可依业务协商，但不得留空。",
        "medium",
        "请结合付款安排和组织政策复核。",
    ),
    (
        "performance_delivery",
        "履行与交付",
        "双方应明确履行内容、交付物、时间节点和交付确认方式。",
        "交付节点可按项目计划调整，但应保留可核验的确认方式。",
        "medium",
        "请补充履行范围、交付物和时间节点。",
    ),
    (
        "acceptance",
        "验收",
        "验收标准、期限、流程和未通过验收的处理方式应当明确。",
        "验收标准可根据具体交付物细化，但不得由单方任意决定。",
        "high",
        "请明确验收标准和未通过验收的处理方式。",
    ),
    (
        "liability",
        "违约责任",
        "违约责任、责任范围和损失承担方式应当清晰且可执行。",
        "责任上限和违约金可依业务协商，但应与实际风险相匹配。",
        "high",
        "请复核责任范围、上限和违约金安排。",
    ),
    (
        "confidentiality",
        "保密",
        "保密信息范围、保密期限、例外和返还或销毁义务应当明确。",
        "保密期限可按信息类型区分，并应保留必要例外。",
        "medium",
        "请复核保密范围、期限及例外。",
    ),
    (
        "intellectual_property",
        "知识产权",
        "成果、交付物及其衍生成果的知识产权归属和使用范围应当明确。",
        "权利归属可按成果类型约定，但应明确许可或转让边界。",
        "high",
        "请明确知识产权归属、许可或转让边界。",
    ),
    (
        "dispute_resolution",
        "争议解决",
        "争议解决方式、管辖地或仲裁机构应当明确。",
        "争议解决安排可依组织政策选择，但应避免表述冲突。",
        "medium",
        "请复核争议解决方式和管辖安排。",
    ),
    (
        "termination",
        "终止与解除",
        "合同终止或解除的条件、通知、交接和后续义务应当明确。",
        "终止通知期限可按业务约定，但应保留必要的善后安排。",
        "high",
        "请补充终止或解除条件及交接义务。",
    ),
)


def _seed_existing_organizations() -> None:
    connection = op.get_bind()
    organization_ids = list(
        connection.execute(sa.text("SELECT id FROM organizations ORDER BY id")).scalars()
    )
    template_table = sa.table(
        "clause_templates",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("normalized_name", sa.String()),
        sa.column("contract_type", sa.String()),
        sa.column("business_scenario", sa.String()),
        sa.column("current_published_version_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    version_table = sa.table(
        "clause_template_versions",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("template_id", sa.Uuid()),
        sa.column("version_no", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("change_note", sa.String()),
        sa.column("effective_at", sa.DateTime(timezone=True)),
    )
    clause_table = sa.table(
        "standard_clauses",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("template_version_id", sa.Uuid()),
        sa.column("clause_key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("standard_text", sa.String()),
        sa.column("allowed_deviation", sa.String()),
        sa.column("severity", sa.String()),
        sa.column("applicability_json", postgresql.JSONB()),
        sa.column("suggestion", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("order_no", sa.Integer()),
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
        for contract_type, name in _BASELINE_TEMPLATES:
            template_id = uuid4()
            version_id = uuid4()
            connection.execute(
                sa.insert(template_table),
                {
                    "id": template_id,
                    "organization_id": organization_id,
                    "name": name,
                    "normalized_name": name.lower(),
                    "contract_type": contract_type,
                    "business_scenario": "standard",
                    "status": "active",
                    "is_default": False,
                },
            )
            connection.execute(
                sa.insert(version_table),
                {
                    "id": version_id,
                    "organization_id": organization_id,
                    "template_id": template_id,
                    "version_no": 1,
                    "status": "published",
                    "change_note": "系统内置演示基线，不代表任何具体企业的法律意见。",
                    "effective_at": effective_at,
                },
            )
            connection.execute(
                sa.insert(clause_table),
                [
                    {
                        "id": uuid4(),
                        "organization_id": organization_id,
                        "template_version_id": version_id,
                        "clause_key": clause_key,
                        "name": clause_name,
                        "standard_text": standard_text,
                        "allowed_deviation": allowed_deviation,
                        "severity": severity,
                        "applicability_json": {},
                        "suggestion": suggestion,
                        "enabled": True,
                        "order_no": order_no,
                    }
                    for order_no, (
                        clause_key,
                        clause_name,
                        standard_text,
                        allowed_deviation,
                        severity,
                        suggestion,
                    ) in enumerate(_BASELINE_CLAUSES, start=1)
                ],
            )
            connection.execute(
                template_table.update()
                .where(template_table.c.id == template_id)
                .values(current_published_version_id=version_id, is_default=True)
            )
            connection.execute(
                sa.insert(audit_table),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "action": "clause_template_version.published",
                    "resource_type": "clause_template_version",
                    "resource_id": version_id,
                    "request_id": "phase8b-migration-baseline",
                    "after_summary_json": {
                        "template_id": str(template_id),
                        "contract_type": contract_type,
                        "business_scenario": "standard",
                        "status": "published",
                        "is_default": True,
                        "effective_at": effective_at.isoformat(),
                        "source": "system_baseline",
                    },
                },
            )


def upgrade() -> None:
    op.create_table(
        "clause_templates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("contract_type", sa.String(length=32), nullable=False),
        sa.Column("business_scenario", sa.String(length=128), nullable=False),
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
        sa.CheckConstraint(
            "contract_type IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment')",
            name="contract_type_valid",
        ),
        sa.CheckConstraint(
            "business_scenario = lower(btrim(business_scenario)) "
            "AND btrim(business_scenario) <> ''",
            name="business_scenario_canonical",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        sa.CheckConstraint(
            "NOT is_default OR (status = 'active' AND current_published_version_id IS NOT NULL)",
            name="default_available",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clause_templates_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_templates"),
        sa.UniqueConstraint("organization_id", "id", name="uq_clause_templates_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id", "normalized_name", name="uq_clause_templates_organization_name"
        ),
    )
    op.create_index(
        "uq_clause_templates_default",
        "clause_templates",
        ["organization_id", "contract_type", "business_scenario"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_clause_templates_organization_scope_created",
        "clause_templates",
        ["organization_id", "contract_type", "business_scenario", "created_at", "id"],
    )

    op.create_table(
        "clause_template_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
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
            ["organization_id", "template_id"],
            ["clause_templates.organization_id", "clause_templates.id"],
            name="fk_clause_template_versions_template_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "published_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_clause_template_versions_publisher_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_template_versions"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_clause_template_versions_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "template_id",
            "version_no",
            name="uq_clause_template_versions_number",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "template_id",
            "id",
            name="uq_clause_template_versions_organization_template_id_id",
        ),
    )
    op.create_index(
        "ix_clause_template_versions_organization_template_version",
        "clause_template_versions",
        ["organization_id", "template_id", "version_no"],
    )

    op.create_table(
        "standard_clauses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("clause_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("standard_text", sa.String(length=10000), nullable=False),
        sa.Column("allowed_deviation", sa.String(length=2000), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "applicability_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("suggestion", sa.String(length=2000), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(clause_key) <> ''", name="clause_key_not_blank"),
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint("btrim(standard_text) <> ''", name="standard_text_not_blank"),
        sa.CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        sa.CheckConstraint("btrim(suggestion) <> ''", name="suggestion_not_blank"),
        sa.CheckConstraint("order_no > 0", name="order_no_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "template_version_id"],
            ["clause_template_versions.organization_id", "clause_template_versions.id"],
            name="fk_standard_clauses_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_standard_clauses"),
        sa.UniqueConstraint("organization_id", "id", name="uq_standard_clauses_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id",
            "template_version_id",
            "clause_key",
            name="uq_standard_clauses_version_key",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "template_version_id",
            "order_no",
            name="uq_standard_clauses_version_order",
        ),
    )
    op.create_index(
        "ix_standard_clauses_organization_version_order",
        "standard_clauses",
        ["organization_id", "template_version_id", "order_no"],
    )

    _seed_existing_organizations()
    op.create_foreign_key(
        "fk_clause_templates_current_version_tenant",
        "clause_templates",
        "clause_template_versions",
        ["organization_id", "id", "current_published_version_id"],
        ["organization_id", "template_id", "id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION enforce_clause_template_current_version_published() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.current_published_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                FROM clause_template_versions
                WHERE organization_id = NEW.organization_id
                  AND template_id = NEW.id
                  AND id = NEW.current_published_version_id
                  AND status = 'published'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'ck_clause_templates_current_version_published',
                    MESSAGE = 'current clause template version must be published';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER clause_templates_current_version_published
        AFTER INSERT OR UPDATE ON clause_templates
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_clause_template_current_version_published()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_published_clause_template_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'published clause template versions are immutable';
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
        CREATE TRIGGER clause_template_versions_immutable
        BEFORE UPDATE OR DELETE ON clause_template_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_published_clause_template_version_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_published_standard_clause_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            source_status varchar(32);
            target_status varchar(32);
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT status INTO source_status
                FROM clause_template_versions
                WHERE organization_id = OLD.organization_id
                  AND id = OLD.template_version_id;
                IF source_status = 'published' THEN
                    RAISE EXCEPTION 'clauses in published template versions are immutable';
                END IF;
            END IF;
            IF TG_OP <> 'DELETE' THEN
                SELECT status INTO target_status
                FROM clause_template_versions
                WHERE organization_id = NEW.organization_id
                  AND id = NEW.template_version_id;
                IF target_status = 'published' THEN
                    RAISE EXCEPTION 'clauses in published template versions are immutable';
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
        CREATE TRIGGER standard_clauses_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON standard_clauses
        FOR EACH ROW EXECUTE FUNCTION prevent_published_standard_clause_mutation()
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only")
    op.execute(
        """
        DELETE FROM audit_logs
        WHERE request_id = 'phase8b-migration-baseline'
          AND action = 'clause_template_version.published'
          AND resource_type = 'clause_template_version'
          AND after_summary_json ->> 'source' = 'system_baseline'
        """
    )
    op.execute("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_append_only")
    op.execute(
        "DROP TRIGGER IF EXISTS clause_templates_current_version_published ON clause_templates"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_clause_template_current_version_published()")
    op.execute("DROP TRIGGER IF EXISTS standard_clauses_immutable ON standard_clauses")
    op.execute("DROP FUNCTION IF EXISTS prevent_published_standard_clause_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS clause_template_versions_immutable ON clause_template_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_published_clause_template_version_mutation()")
    op.drop_constraint(
        "fk_clause_templates_current_version_tenant", "clause_templates", type_="foreignkey"
    )
    op.drop_index("ix_standard_clauses_organization_version_order", table_name="standard_clauses")
    op.drop_table("standard_clauses")
    op.drop_index(
        "ix_clause_template_versions_organization_template_version",
        table_name="clause_template_versions",
    )
    op.drop_table("clause_template_versions")
    op.drop_index(
        "ix_clause_templates_organization_scope_created", table_name="clause_templates"
    )
    op.drop_index("uq_clause_templates_default", table_name="clause_templates")
    op.drop_table("clause_templates")
