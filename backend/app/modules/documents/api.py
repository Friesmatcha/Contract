from collections import defaultdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.api import _read_context
from backend.app.modules.contracts.models import Contract, ContractFile
from backend.app.modules.contracts.service import get_contract
from backend.app.modules.documents.models import (
    DocumentBlock,
    DocumentPage,
    DocumentVersion,
    SourceSpan,
)
from backend.app.modules.documents.schemas import (
    DocumentBlockResponse,
    DocumentBlocksResponse,
    DocumentPageResponse,
    SourceSpanResponse,
)
from backend.app.modules.documents.service import source_kind
from backend.app.modules.identity.api import Authenticated
from backend.app.modules.identity.service import AuthenticatedSession
from backend.app.shared.errors import ApplicationError

router = APIRouter(prefix="/documents", tags=["document parsing and evidence"])


def _document_not_found(code: str = "DOCUMENT_NOT_FOUND") -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code=code,
        message="文档不存在。",
    )


def _document_not_ready() -> ApplicationError:
    return ApplicationError(
        status_code=409,
        code="DOCUMENT_NOT_READY",
        message="文档仍在解析或解析失败，请稍后重试。",
    )


def _load_document_scope(
    database: DatabaseSession,
    *,
    document_version_id: UUID,
    request: Request,
    authenticated: AuthenticatedSession,
    organization_id: UUID | None,
    support_grant_id: UUID | None,
    not_found_code: str = "DOCUMENT_NOT_FOUND",
) -> tuple[DocumentVersion, str | None]:
    row = database.execute(
        select(DocumentVersion, ContractFile, Contract)
        .join(
            ContractFile,
            (ContractFile.organization_id == DocumentVersion.organization_id)
            & (ContractFile.id == DocumentVersion.contract_file_id),
        )
        .join(
            Contract,
            (Contract.organization_id == ContractFile.organization_id)
            & (Contract.id == ContractFile.contract_id),
        )
        .where(DocumentVersion.id == document_version_id)
    ).one_or_none()
    if row is None:
        raise _document_not_found(not_found_code)
    document, contract_file, _contract = row
    try:
        scoped_organization_id, role = _read_context(
            database,
            authenticated=authenticated,
            organization_id=organization_id or document.organization_id,
            support_grant_id=support_grant_id,
            request_id=request.state.request_id,
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise _document_not_found(not_found_code) from exc
        raise
    if scoped_organization_id != document.organization_id:
        raise _document_not_found(not_found_code)
    if support_grant_id is None and role == "viewer":
        try:
            get_contract(
                database,
                organization_id=document.organization_id,
                contract_id=contract_file.contract_id,
                viewer_user_id=authenticated.user.id,
            )
        except ApplicationError as exc:
            if exc.status_code == 404:
                raise _document_not_found(not_found_code) from exc
            raise
    return document, role


def _source_payload(
    document: DocumentVersion,
    block: DocumentBlock,
    page_no: int | None,
    span: SourceSpan,
) -> dict[str, object]:
    return {
        "document_version_id": document.id,
        "kind": source_kind(document, block),
        "page_no": page_no,
        "paragraph_no": block.paragraph_no,
        "table_path": block.table_path,
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
        "bbox": span.bbox_json,
        "quote": span.quote,
    }


def _blocks_payload(
    database: DatabaseSession,
    document: DocumentVersion,
    *,
    page_no: int | None = None,
    include_source_spans: bool = True,
) -> list[DocumentBlockResponse]:
    statement = (
        select(DocumentBlock, DocumentPage.page_no)
        .outerjoin(
            DocumentPage,
            (DocumentPage.organization_id == DocumentBlock.organization_id)
            & (DocumentPage.id == DocumentBlock.page_id),
        )
        .where(
            DocumentBlock.organization_id == document.organization_id,
            DocumentBlock.document_version_id == document.id,
        )
        .order_by(DocumentBlock.order_no)
    )
    if page_no is not None:
        statement = statement.where(DocumentPage.page_no == page_no)
    rows = database.execute(statement).all()
    block_ids = [block.id for block, _ in rows]
    spans_by_block: dict[UUID, list[SourceSpan]] = defaultdict(list)
    if include_source_spans and block_ids:
        spans = database.scalars(
            select(SourceSpan)
            .where(
                SourceSpan.organization_id == document.organization_id,
                SourceSpan.document_version_id == document.id,
                SourceSpan.block_id.in_(block_ids),
            )
            .order_by(SourceSpan.created_at, SourceSpan.id)
        ).all()
        for span in spans:
            if span.block_id is not None:
                spans_by_block[span.block_id].append(span)
    return [
        DocumentBlockResponse.model_validate(
            {
                "id": block.id,
                "order_no": block.order_no,
                "block_type": block.block_type,
                "page_no": physical_page_no,
                "paragraph_no": block.paragraph_no,
                "table_path": block.table_path,
                "text": block.text,
                "bbox": block.bbox_json,
                "source_spans": [
                    SourceSpanResponse.model_validate(
                        _source_payload(document, block, physical_page_no, span)
                    )
                    for span in spans_by_block[block.id]
                ],
            }
        )
        for block, physical_page_no in rows
    ]


@router.get(
    "/{document_version_id}/pages/{page_no}",
    response_model=DocumentPageResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def get_document_page(
    document_version_id: UUID,
    page_no: Annotated[int, Path(ge=1)],
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    include_blocks: Annotated[bool, Query()] = True,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
) -> DocumentPageResponse:
    document, _ = _load_document_scope(
        database,
        document_version_id=document_version_id,
        request=request,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
        not_found_code="DOCUMENT_OR_PAGE_NOT_FOUND",
    )
    if document.status != "succeeded":
        raise _document_not_ready()
    page = database.scalar(
        select(DocumentPage).where(
            DocumentPage.organization_id == document.organization_id,
            DocumentPage.document_version_id == document.id,
            DocumentPage.page_no == page_no,
        )
    )
    if page is None:
        raise _document_not_found("DOCUMENT_OR_PAGE_NOT_FOUND")
    if page.page_no is None:
        raise _document_not_found("DOCUMENT_OR_PAGE_NOT_FOUND")
    return DocumentPageResponse(
        document_version_id=document.id,
        document_kind=document.parser_name,
        page_no=page.page_no,
        page_count=document.page_count,
        width=page.width,
        height=page.height,
        text=page.text,
        image_file_id=page.image_file_id,
        ocr_status=page.ocr_status,
        ocr_confidence=page.ocr_confidence,
        error_code=page.error_code,
        error_message=page.error_message,
        blocks=(
            _blocks_payload(database, document, page_no=page_no)
            if include_blocks
            else []
        ),
    )


@router.get(
    "/{document_version_id}/blocks",
    response_model=DocumentBlocksResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def get_document_blocks(
    document_version_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    include_source_spans: Annotated[bool, Query()] = True,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
) -> DocumentBlocksResponse:
    document, _ = _load_document_scope(
        database,
        document_version_id=document_version_id,
        request=request,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
    )
    if document.status != "succeeded":
        raise _document_not_ready()
    return DocumentBlocksResponse(
        document_version_id=document.id,
        document_kind=document.parser_name,
        page_count=document.page_count,
        blocks=_blocks_payload(
            database,
            document,
            include_source_spans=include_source_spans,
        ),
    )
