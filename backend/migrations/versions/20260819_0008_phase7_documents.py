"""Add Phase 7 document parsing, OCR and evidence tables.

Revision ID: 20260819_0008
Revises: 20260819_0007
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0008"
down_revision: str | None = "20260819_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contract_file_id", sa.Uuid(), nullable=False),
        sa.Column("parser_name", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("parse_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=True),
        sa.Column("ocr_status", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
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
        sa.CheckConstraint("parser_name IN ('docx', 'pdf', 'image')", name="parser_name_valid"),
        sa.CheckConstraint(
            "ocr_status IN ("
            "'not_required', 'pending', 'completed', 'low_confidence', 'partial', 'failed'"
            ")",
            name="ocr_status_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="status_valid",
        ),
        sa.CheckConstraint("page_count >= 0", name="page_count_nonnegative"),
        sa.CheckConstraint(
            "text_sha256 IS NULL OR text_sha256 ~ '^[0-9a-f]{64}$'",
            name="text_sha256_hex",
        ),
        sa.CheckConstraint(
            "parse_fingerprint ~ '^[0-9a-f]{64}$'",
            name="parse_fingerprint_hex",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_file_id"],
            ["contract_files.organization_id", "contract_files.id"],
            name="fk_document_versions_contract_file_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_document_versions_organization_id_id"
        ),
    )
    op.create_index(
        "uq_document_versions_input_fingerprint",
        "document_versions",
        ["organization_id", "parse_fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_document_versions_organization_contract_file",
        "document_versions",
        ["organization_id", "contract_file_id", "created_at"],
    )

    op.create_table(
        "document_pages",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("image_file_id", sa.Uuid(), nullable=True),
        sa.Column("ocr_status", sa.String(length=32), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
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
        sa.CheckConstraint("page_no IS NULL OR page_no > 0", name="page_no_positive"),
        sa.CheckConstraint(
            "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
            name="ocr_confidence_range",
        ),
        sa.CheckConstraint(
            "ocr_status IN ("
            "'not_required', 'pending', 'completed', 'low_confidence', 'blank', 'failed'"
            ")",
            name="ocr_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_document_pages_document_version_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "image_file_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_document_pages_image_file_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_pages"),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_pages_organization_id_id"),
    )
    op.create_index(
        "uq_document_pages_document_page",
        "document_pages",
        ["organization_id", "document_version_id", "page_no"],
        unique=True,
    )
    op.create_index(
        "ix_document_pages_organization_document_page",
        "document_pages",
        ["organization_id", "document_version_id", "page_no"],
    )

    op.create_table(
        "document_blocks",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=True),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("paragraph_no", sa.Integer(), nullable=True),
        sa.Column("table_path", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("bbox_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint("order_no > 0", name="order_no_positive"),
        sa.CheckConstraint("btrim(text) <> ''", name="text_not_blank"),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_document_blocks_document_version_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "page_id"],
            ["document_pages.organization_id", "document_pages.id"],
            name="fk_document_blocks_page_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_blocks"),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_blocks_organization_id_id"),
    )
    op.create_index(
        "uq_document_blocks_document_order",
        "document_blocks",
        ["organization_id", "document_version_id", "order_no"],
        unique=True,
    )
    op.create_index(
        "ix_document_blocks_document_page_order",
        "document_blocks",
        ["organization_id", "document_version_id", "page_id", "order_no"],
    )

    op.create_table(
        "source_spans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=True),
        sa.Column("block_id", sa.Uuid(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("bbox_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_sha256", sa.String(length=64), nullable=False),
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
        sa.CheckConstraint(
            "page_id IS NOT NULL OR block_id IS NOT NULL",
            name="source_target_required",
        ),
        sa.CheckConstraint("start_offset >= 0", name="start_offset_nonnegative"),
        sa.CheckConstraint("end_offset >= start_offset", name="end_offset_valid"),
        sa.CheckConstraint("quote_sha256 ~ '^[0-9a-f]{64}$'", name="quote_sha256_hex"),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_source_spans_document_version_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "page_id"],
            ["document_pages.organization_id", "document_pages.id"],
            name="fk_source_spans_page_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "block_id"],
            ["document_blocks.organization_id", "document_blocks.id"],
            name="fk_source_spans_block_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_spans"),
        sa.UniqueConstraint("organization_id", "id", name="uq_source_spans_organization_id_id"),
    )
    op.create_index(
        "ix_source_spans_document_block",
        "source_spans",
        ["organization_id", "document_version_id", "block_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_spans_document_block", table_name="source_spans")
    op.drop_table("source_spans")
    op.drop_index("ix_document_blocks_document_page_order", table_name="document_blocks")
    op.drop_index("uq_document_blocks_document_order", table_name="document_blocks")
    op.drop_table("document_blocks")
    op.drop_index("ix_document_pages_organization_document_page", table_name="document_pages")
    op.drop_index("uq_document_pages_document_page", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index("ix_document_versions_organization_contract_file", table_name="document_versions")
    op.drop_index("uq_document_versions_input_fingerprint", table_name="document_versions")
    op.drop_table("document_versions")
