import { apiFetch } from '@/api/client'
import type { DocumentBlocksResponse, DocumentPageResponse } from '@/api/types'

const API_BASE = '/api/v1'

function documentPath(documentVersionId: string): string {
  return `${API_BASE}/documents/${encodeURIComponent(documentVersionId)}`
}

export function getDocumentPage(
  documentVersionId: string,
  pageNo: number,
  organizationId?: string,
): Promise<DocumentPageResponse> {
  const headers: HeadersInit = organizationId ? { 'X-Organization-ID': organizationId } : {}
  return apiFetch(`${documentPath(documentVersionId)}/pages/${pageNo}?include_blocks=true`, { headers })
}

export function getDocumentBlocks(
  documentVersionId: string,
  organizationId?: string,
): Promise<DocumentBlocksResponse> {
  const headers: HeadersInit = organizationId ? { 'X-Organization-ID': organizationId } : {}
  return apiFetch(`${documentPath(documentVersionId)}/blocks?include_source_spans=true`, { headers })
}

export function documentFileDownloadUrl(
  fileId: string,
  disposition: 'attachment' | 'inline' = 'inline',
): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}/download?disposition=${disposition}`
}

