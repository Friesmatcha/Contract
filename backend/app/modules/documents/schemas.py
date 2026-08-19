from typing import Literal
from uuid import UUID

from pydantic import BaseModel

DocumentKind = Literal["docx", "pdf", "image"]
SourceKind = Literal["pdf_page", "image_page", "docx_paragraph", "docx_table_cell"]


class SourceSpanResponse(BaseModel):
    document_version_id: UUID
    kind: SourceKind
    page_no: int | None
    paragraph_no: int | None
    table_path: str | None
    start_offset: int
    end_offset: int
    bbox: dict[str, float] | None
    quote: str


class DocumentBlockResponse(BaseModel):
    id: UUID
    order_no: int
    block_type: str
    page_no: int | None
    paragraph_no: int | None
    table_path: str | None
    text: str
    bbox: dict[str, float] | None
    source_spans: list[SourceSpanResponse]


class DocumentPageResponse(BaseModel):
    document_version_id: UUID
    document_kind: DocumentKind
    page_no: int
    page_count: int
    width: float | None
    height: float | None
    text: str
    image_file_id: UUID | None
    ocr_status: str
    ocr_confidence: float | None
    error_code: str | None
    error_message: str | None
    blocks: list[DocumentBlockResponse]


class DocumentBlocksResponse(BaseModel):
    document_version_id: UUID
    document_kind: DocumentKind
    page_count: int
    blocks: list[DocumentBlockResponse]

