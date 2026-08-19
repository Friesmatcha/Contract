import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type {
  CreateOrganizationRequest,
  CreateSupportAccessGrantRequest,
  CursorPage,
  InviteMemberRequest,
  Membership,
  OrganizationMemberListQuery,
  Organization,
  OrganizationProfile,
  OrganizationSettings,
  PlatformModelConfiguration,
  PlatformOrganizationListItem,
  PlatformOrganizationListQuery,
  SupportAccessGrant,
  SupportAccessGrantListQuery,
  UpdateMemberRequest,
  UpdateOrganizationRequest,
  UpdateOrganizationSettingsRequest,
  UpdatePlatformModelConfigurationRequest,
} from '@/api/types'

const API_BASE = '/api/v1'

export type OrganizationApiErrorCode =
  | 'ACTIVE_SUPPORT_GRANT_EXISTS'
  | 'AUTHENTICATION_REQUIRED'
  | 'LAST_ORG_ADMIN'
  | 'MEMBER_NOT_FOUND'
  | 'MEMBER_NOT_PENDING_INVITATION'
  | 'MEMBERSHIP_ALREADY_EXISTS'
  | 'MODEL_ENVIRONMENT_NOT_CONFIGURED'
  | 'ORGANIZATION_NAME_CONFLICT'
  | 'ORGANIZATION_NOT_FOUND'
  | 'ORG_ADMIN_REQUIRED'
  | 'PLATFORM_ADMIN_NOT_FOUND'
  | 'PLATFORM_ADMIN_REQUIRED'
  | 'RATE_LIMITED'
  | 'RESOURCE_VERSION_CONFLICT'
  | 'SMTP_NOT_CONFIGURED'
  | 'SUPPORT_GRANT_DURATION_INVALID'
  | 'VALIDATION_ERROR'

function organizationPath(organizationId: string): string {
  return `${API_BASE}/organizations/${encodeURIComponent(organizationId)}`
}

function appendQuery(path: string, query: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query) as Array<[string, unknown]>) {
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

export function listOrganizationMembers(
  organizationId: string,
  query: OrganizationMemberListQuery = {},
): Promise<CursorPage<Membership>> {
  return apiFetch(appendQuery(`${organizationPath(organizationId)}/members`, query))
}

export function inviteOrganizationMember(
  organizationId: string,
  body: InviteMemberRequest,
  idempotencyKey: string,
): Promise<Membership> {
  return apiFetch(`${organizationPath(organizationId)}/members`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function resendOrganizationInvitation(
  memberId: string,
  idempotencyKey: string,
): Promise<Membership> {
  return apiFetch(`${API_BASE}/members/${encodeURIComponent(memberId)}/resend-invitation`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({}),
  })
}

export function updateOrganizationMember(
  memberId: string,
  body: UpdateMemberRequest,
): Promise<Membership> {
  return apiFetch(`${API_BASE}/members/${encodeURIComponent(memberId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function listSupportAccessGrants(
  organizationId: string,
  query: SupportAccessGrantListQuery = {},
): Promise<CursorPage<SupportAccessGrant>> {
  return apiFetch(appendQuery(`${organizationPath(organizationId)}/support-access-grants`, query))
}

export function createSupportAccessGrant(
  organizationId: string,
  body: CreateSupportAccessGrantRequest,
  idempotencyKey: string,
): Promise<SupportAccessGrant> {
  return apiFetch(`${organizationPath(organizationId)}/support-access-grants`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function revokeSupportAccessGrant(organizationId: string, grantId: string): Promise<void> {
  return apiFetch(`${organizationPath(organizationId)}/support-access-grants/${encodeURIComponent(grantId)}`, {
    method: 'DELETE',
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
