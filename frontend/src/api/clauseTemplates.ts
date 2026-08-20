import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type {
  ClauseTemplate,
  ClauseTemplateDetail,
  ClauseTemplateListQuery,
  ClauseTemplateVersion,
  CreateClauseTemplateRequest,
  CreateClauseTemplateVersionRequest,
  CursorPage,
  UpdateClauseTemplateRequest,
  UpdateClauseTemplateVersionRequest,
} from '@/api/types'

const API_BASE = '/api/v1'

export type ClauseTemplateApiErrorCode =
  | 'CLAUSE_SCHEMA_INVALID'
  | 'DEFAULT_CLAUSE_TEMPLATE_CONFLICT'
  | 'DEFAULT_CLAUSE_TEMPLATE_REQUIRED'
  | 'FORBIDDEN'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'ORGANIZATION_CONTEXT_REQUIRED'
  | 'ORGANIZATION_NOT_FOUND'
  | 'ORG_ADMIN_REQUIRED'
  | 'RESOURCE_VERSION_CONFLICT'
  | 'TEMPLATE_DISABLED'
  | 'TEMPLATE_NAME_CONFLICT'
  | 'TEMPLATE_NOT_FOUND'
  | 'TEMPLATE_VERSION_NOT_FOUND'
  | 'VERSION_ALREADY_PUBLISHED'
  | 'VERSION_NOT_DRAFT'
  | 'VERSION_SOURCE_INVALID'
  | 'VALIDATION_ERROR'

function appendQuery(path: string, query: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query) as Array<[string, unknown]>) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `${path}?${serialized}` : path
}

function organizationHeaders(organizationId: string): HeadersInit {
  return { 'X-Organization-ID': organizationId }
}

function idempotencyHeaders(organizationId: string, key: string): HeadersInit {
  return { ...organizationHeaders(organizationId), 'Idempotency-Key': key }
}

function templatePath(templateId: string): string {
  return `${API_BASE}/clause-templates/${encodeURIComponent(templateId)}`
}

function versionPath(versionId: string): string {
  return `${API_BASE}/clause-template-versions/${encodeURIComponent(versionId)}`
}

export function isClauseTemplateApiError<Code extends ClauseTemplateApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function listClauseTemplates(
  organizationId: string,
  query: ClauseTemplateListQuery = {},
): Promise<CursorPage<ClauseTemplate>> {
  return apiFetch(appendQuery(`${API_BASE}/clause-templates`, query), {
    headers: organizationHeaders(organizationId),
  })
}

export function createClauseTemplate(
  organizationId: string,
  body: CreateClauseTemplateRequest,
  idempotencyKey: string,
): Promise<ClauseTemplate> {
  return apiFetch(`${API_BASE}/clause-templates`, {
    method: 'POST',
    headers: idempotencyHeaders(organizationId, idempotencyKey),
    body: JSON.stringify(body),
  })
}

export function getClauseTemplate(
  templateId: string,
  includeClauses = false,
): Promise<ClauseTemplateDetail> {
  return apiFetch(appendQuery(templatePath(templateId), { include_clauses: includeClauses }))
}

export function updateClauseTemplate(
  templateId: string,
  body: UpdateClauseTemplateRequest,
): Promise<ClauseTemplate> {
  return apiFetch(templatePath(templateId), { method: 'PATCH', body: JSON.stringify(body) })
}

export function createClauseTemplateVersion(
  templateId: string,
  body: CreateClauseTemplateVersionRequest,
  idempotencyKey: string,
): Promise<ClauseTemplateVersion> {
  return apiFetch(`${templatePath(templateId)}/versions`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getClauseTemplateVersion(versionId: string): Promise<ClauseTemplateVersion> {
  return apiFetch(versionPath(versionId))
}

export function updateClauseTemplateVersion(
  versionId: string,
  body: UpdateClauseTemplateVersionRequest,
): Promise<ClauseTemplateVersion> {
  return apiFetch(versionPath(versionId), { method: 'PATCH', body: JSON.stringify(body) })
}

export function publishClauseTemplateVersion(versionId: string): Promise<ClauseTemplateVersion> {
  return apiFetch(`${versionPath(versionId)}/publish`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
