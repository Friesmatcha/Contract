from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin


class DocumentVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contract_file_id"],
            ["contract_files.organization_id", "contract_files.id"],
            name="fk_document_versions_contract_file_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "parser_name IN ('docx', 'pdf', 'image')",
            name="parser_name_valid",
        ),
        CheckConstraint(
            "ocr_status IN ("
            "'not_required', 'pending', 'completed', 'low_confidence', 'partial', 'failed'"
            ")",
            name="ocr_status_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="status_valid",
        ),
        CheckConstraint("page_count >= 0", name="page_count_nonnegative"),
        CheckConstraint(
            "text_sha256 IS NULL OR text_sha256 ~ '^[0-9a-f]{64}$'",
            name="text_sha256_hex",
        ),
        CheckConstraint("parse_fingerprint ~ '^[0-9a-f]{64}$'", name="parse_fingerprint_hex"),
        UniqueConstraint("organization_id", "id", name="uq_document_versions_organization_id_id"),
        Index(
            "uq_document_versions_input_fingerprint",
            "organization_id",
            "parse_fingerprint",
            unique=True,
        ),
        Index(
            "ix_document_versions_organization_contract_file",
            "organization_id",
            "contract_file_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_file_id: Mapped[UUID] = mapped_column(nullable=False)
    parser_name: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    text_sha256: Mapped[str | None] = mapped_column(String(64))
    ocr_status: Mapped[str] = mapped_column(String(32), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))


class DocumentPage(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_document_pages_document_version_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "image_file_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_document_pages_image_file_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("page_no IS NULL OR page_no > 0", name="page_no_positive"),
        CheckConstraint(
            "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
            name="ocr_confidence_range",
        ),
        CheckConstraint(
            "ocr_status IN ("
            "'not_required', 'pending', 'completed', 'low_confidence', 'blank', 'failed'"
            ")",
            name="ocr_status_valid",
        ),
        UniqueConstraint("organization_id", "id", name="uq_document_pages_organization_id_id"),
        Index(
            "uq_document_pages_document_page",
            "organization_id",
            "document_version_id",
            "page_no",
            unique=True,
        ),
        Index(
            "ix_document_pages_organization_document_page",
            "organization_id",
            "document_version_id",
            "page_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[float | None] = mapped_column(Float)
    height: Mapped[float | None] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    image_file_id: Mapped[UUID | None] = mapped_column()
    ocr_status: Mapped[str] = mapped_column(String(32), nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))


class DocumentBlock(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_blocks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_document_blocks_document_version_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "page_id"],
            ["document_pages.organization_id", "document_pages.id"],
            name="fk_document_blocks_page_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint("order_no > 0", name="order_no_positive"),
        CheckConstraint("btrim(text) <> ''", name="text_not_blank"),
        UniqueConstraint("organization_id", "id", name="uq_document_blocks_organization_id_id"),
        Index(
            "uq_document_blocks_document_order",
            "organization_id",
            "document_version_id",
            "order_no",
            unique=True,
        ),
        Index(
            "ix_document_blocks_document_page_order",
            "organization_id",
            "document_version_id",
            "page_id",
            "order_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    page_id: Mapped[UUID | None] = mapped_column()
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    paragraph_no: Mapped[int | None] = mapped_column(Integer)
    table_path: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox_json: Mapped[dict[str, float] | None] = mapped_column(JSONB)


class SourceSpan(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_spans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_source_spans_document_version_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "page_id"],
            ["document_pages.organization_id", "document_pages.id"],
            name="fk_source_spans_page_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "block_id"],
            ["document_blocks.organization_id", "document_blocks.id"],
            name="fk_source_spans_block_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "page_id IS NOT NULL OR block_id IS NOT NULL",
            name="source_target_required",
        ),
        CheckConstraint("start_offset >= 0", name="start_offset_nonnegative"),
        CheckConstraint("end_offset >= start_offset", name="end_offset_valid"),
        CheckConstraint("quote_sha256 ~ '^[0-9a-f]{64}$'", name="quote_sha256_hex"),
        UniqueConstraint("organization_id", "id", name="uq_source_spans_organization_id_id"),
        Index(
            "ix_source_spans_document_block",
            "organization_id",
            "document_version_id",
            "block_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    page_id: Mapped[UUID | None] = mapped_column()
    block_id: Mapped[UUID | None] = mapped_column()
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_json: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
