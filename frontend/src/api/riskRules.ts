import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type {
  CreateRiskRuleBundleRequest,
  CreateRiskRuleVersionRequest,
  CursorPage,
  RiskRuleBundle,
  RiskRuleBundleDetail,
  RiskRuleListQuery,
  RiskRuleVersion,
  UpdateRiskRuleBundleRequest,
  UpdateRiskRuleVersionRequest,
} from '@/api/types'

const API_BASE = '/api/v1'

export type RiskRuleApiErrorCode =
  | 'DEFAULT_RULE_BUNDLE_CONFLICT'
  | 'DEFAULT_RULE_BUNDLE_REQUIRED'
  | 'FORBIDDEN'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'ORGANIZATION_CONTEXT_REQUIRED'
  | 'ORGANIZATION_NOT_FOUND'
  | 'ORG_ADMIN_REQUIRED'
  | 'RESOURCE_VERSION_CONFLICT'
  | 'RULE_BUNDLE_DISABLED'
  | 'RULE_BUNDLE_NAME_CONFLICT'
  | 'RULE_BUNDLE_NOT_FOUND'
  | 'RULE_SCHEMA_INVALID'
  | 'RULE_VERSION_NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'VERSION_ALREADY_PUBLISHED'
  | 'VERSION_SOURCE_INVALID'
  | 'VERSION_NOT_DRAFT'

function organizationHeaders(organizationId: string): HeadersInit {
  return { 'X-Organization-ID': organizationId }
}

function appendQuery(path: string, query: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query) as Array<[string, unknown]>) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `${path}?${serialized}` : path
}

function bundlePath(bundleId: string): string {
  return `${API_BASE}/risk-rule-bundles/${encodeURIComponent(bundleId)}`
}

function versionPath(versionId: string): string {
  return `${API_BASE}/risk-rule-bundle-versions/${encodeURIComponent(versionId)}`
}

function idempotencyHeaders(organizationId: string, idempotencyKey: string): HeadersInit {
  return {
    ...organizationHeaders(organizationId),
    'Idempotency-Key': idempotencyKey,
  }
}

function resourceIdempotencyHeaders(idempotencyKey: string): HeadersInit {
  return { 'Idempotency-Key': idempotencyKey }
}

export function isRiskRuleApiError<Code extends RiskRuleApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function listRiskRuleBundles(
  organizationId: string,
  query: RiskRuleListQuery = {},
): Promise<CursorPage<RiskRuleBundle>> {
  return apiFetch(appendQuery(`${API_BASE}/risk-rule-bundles`, query), {
    headers: organizationHeaders(organizationId),
  })
}

export function createRiskRuleBundle(
  organizationId: string,
  body: CreateRiskRuleBundleRequest,
  idempotencyKey: string,
): Promise<RiskRuleBundle> {
  return apiFetch(`${API_BASE}/risk-rule-bundles`, {
    method: 'POST',
    headers: idempotencyHeaders(organizationId, idempotencyKey),
    body: JSON.stringify(body),
  })
}

export function getRiskRuleBundle(
  bundleId: string,
  includeRules = false,
): Promise<RiskRuleBundleDetail> {
  const path = appendQuery(bundlePath(bundleId), { include_rules: includeRules })
  return apiFetch(path)
}

export function updateRiskRuleBundle(
  bundleId: string,
  body: UpdateRiskRuleBundleRequest,
): Promise<RiskRuleBundle> {
  return apiFetch(bundlePath(bundleId), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function createRiskRuleVersion(
  bundleId: string,
  body: CreateRiskRuleVersionRequest,
  idempotencyKey: string,
): Promise<RiskRuleVersion> {
  return apiFetch(`${bundlePath(bundleId)}/versions`, {
    method: 'POST',
    headers: resourceIdempotencyHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
}

export function getRiskRuleVersion(
  versionId: string,
): Promise<RiskRuleVersion> {
  return apiFetch(versionPath(versionId))
}

export function updateRiskRuleVersion(
  versionId: string,
  body: UpdateRiskRuleVersionRequest,
): Promise<RiskRuleVersion> {
  return apiFetch(versionPath(versionId), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function publishRiskRuleVersion(
  versionId: string,
): Promise<RiskRuleVersion> {
  return apiFetch(`${versionPath(versionId)}/publish`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
