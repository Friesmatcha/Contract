import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type {
  CreateOrganizationRequest,
  CursorPage,
  Organization,
  OrganizationProfile,
  OrganizationSettings,
  PlatformModelConfiguration,
  PlatformOrganizationListItem,
  PlatformOrganizationListQuery,
  UpdateOrganizationRequest,
  UpdateOrganizationSettingsRequest,
  UpdatePlatformModelConfigurationRequest,
} from '@/api/types'

const API_BASE = '/api/v1'

export type OrganizationApiErrorCode =
  | 'AUTHENTICATION_REQUIRED'
  | 'MODEL_ENVIRONMENT_NOT_CONFIGURED'
  | 'ORGANIZATION_NAME_CONFLICT'
  | 'ORGANIZATION_NOT_FOUND'
  | 'ORG_ADMIN_REQUIRED'
  | 'PLATFORM_ADMIN_REQUIRED'
  | 'RESOURCE_VERSION_CONFLICT'
  | 'VALIDATION_ERROR'

function organizationPath(organizationId: string): string {
  return `${API_BASE}/organizations/${encodeURIComponent(organizationId)}`
}

function appendQuery(path: string, query: PlatformOrganizationListQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `${path}?${serialized}` : path
}

export function isOrganizationApiError<Code extends OrganizationApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function listPlatformOrganizations(
  query: PlatformOrganizationListQuery = {},
): Promise<CursorPage<PlatformOrganizationListItem>> {
  return apiFetch(appendQuery(`${API_BASE}/platform/organizations`, query))
}

export function createPlatformOrganization(
  body: CreateOrganizationRequest,
  idempotencyKey: string,
): Promise<Organization> {
  return apiFetch(`${API_BASE}/platform/organizations`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getPlatformOrganization(organizationId: string): Promise<Organization> {
  return apiFetch(`${API_BASE}/platform/organizations/${encodeURIComponent(organizationId)}`)
}

export function updatePlatformOrganization(
  organizationId: string,
  body: UpdateOrganizationRequest,
): Promise<Organization> {
  return apiFetch(`${API_BASE}/platform/organizations/${encodeURIComponent(organizationId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function getOrganizationProfile(organizationId: string): Promise<OrganizationProfile> {
  return apiFetch(organizationPath(organizationId))
}

export function getOrganizationSettings(organizationId: string): Promise<OrganizationSettings> {
  return apiFetch(`${organizationPath(organizationId)}/settings`)
}

export function updateOrganizationSettings(
  organizationId: string,
  body: UpdateOrganizationSettingsRequest,
): Promise<OrganizationSettings> {
  return apiFetch(`${organizationPath(organizationId)}/settings`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function getPlatformModelConfiguration(): Promise<PlatformModelConfiguration> {
  return apiFetch(`${API_BASE}/platform/model-configuration`)
}

export function updatePlatformModelConfiguration(
  body: UpdatePlatformModelConfigurationRequest,
): Promise<PlatformModelConfiguration> {
  return apiFetch(`${API_BASE}/platform/model-configuration`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}
