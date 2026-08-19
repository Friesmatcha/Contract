import { setCsrfToken } from '@/features/auth/csrf'
import {
  createPlatformOrganization,
  createSupportAccessGrant,
  getOrganizationProfile,
  getOrganizationSettings,
  getPlatformModelConfiguration,
  getPlatformOrganization,
  isOrganizationApiError,
  inviteOrganizationMember,
  listOrganizationMembers,
  listPlatformOrganizations,
  listSupportAccessGrants,
  resendOrganizationInvitation,
  revokeSupportAccessGrant,
  updateOrganizationSettings,
  updateOrganizationMember,
  updatePlatformModelConfiguration,
  updatePlatformOrganization,
} from '@/api/organizations'
import { ApiError } from '@/api/client'
import { afterEach, expect, test, vi } from 'vitest'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

function requestInit(fetchMock: ReturnType<typeof vi.spyOn>, callIndex: number): RequestInit {
  return fetchMock.mock.calls[callIndex]?.[1] ?? {}
}

afterEach(() => {
  setCsrfToken(null)
})

test('maps platform organization filters and cursor pagination into the contract query', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse({ items: [], next_cursor: null, has_more: false }),
  )

  await listPlatformOrganizations({
    q: 'Acme & Co',
    status: 'active',
    sort: 'name',
    direction: 'asc',
    limit: 50,
    cursor: 'cursor+value',
  })

  expect(fetchMock.mock.calls[0]?.[0]).toBe(
    '/api/v1/platform/organizations?q=Acme+%26+Co&status=active&sort=name&direction=asc&limit=50&cursor=cursor%2Bvalue',
  )
})

test('creates an organization with its idempotency key and the current CSRF token', async () => {
  setCsrfToken('csrf-current')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ id: 'org-1' }))

  await createPlatformOrganization(
    {
      name: '示例企业',
      initial_admin_email: 'admin@example.com',
      retention_days: 180,
    },
    'organization-create-1',
  )

  const init = requestInit(fetchMock, 0)
  const headers = new Headers(init.headers)
  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/platform/organizations')
  expect(init.method).toBe('POST')
  expect(headers.get('Idempotency-Key')).toBe('organization-create-1')
  expect(headers.get('X-CSRF-Token')).toBe('csrf-current')
  expect(init.body).toBe(
    JSON.stringify({
      name: '示例企业',
      initial_admin_email: 'admin@example.com',
      retention_days: 180,
    }),
  )
})

test('uses platform organization resource paths and PATCH bodies', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse({ id: 'org/1' }))
    .mockResolvedValueOnce(jsonResponse({ id: 'org/1' }))

  await getPlatformOrganization('org/1')
  await updatePlatformOrganization('org/1', { status: 'disabled', version: 3 })

  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/platform/organizations/org%2F1')
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/platform/organizations/org%2F1')
  expect(requestInit(fetchMock, 1)).toMatchObject({
    method: 'PATCH',
    body: JSON.stringify({ status: 'disabled', version: 3 }),
  })
})

test('uses organization profile and settings resource paths with PATCH request bodies', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse({ id: 'org-1' }))
    .mockResolvedValueOnce(jsonResponse({ version: 1 }))
    .mockResolvedValueOnce(jsonResponse({ version: 2 }))

  await getOrganizationProfile('org-1')
  await getOrganizationSettings('org-1')
  await updateOrganizationSettings('org-1', {
    warn_on_medium_risk: true,
    report_watermark: '内部资料',
    version: 1,
  })

  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/organizations/org-1')
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/organizations/org-1/settings')
  expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/organizations/org-1/settings')
  expect(requestInit(fetchMock, 2)).toMatchObject({
    method: 'PATCH',
    body: JSON.stringify({
      warn_on_medium_risk: true,
      report_watermark: '内部资料',
      version: 1,
    }),
  })
})

test('uses the platform model configuration route and exposes documented error codes', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse({ version: 1 }))
    .mockResolvedValueOnce(jsonResponse({ version: 2 }))

  await getPlatformModelConfiguration()
  await updatePlatformModelConfiguration({
    timeout_seconds: 60,
    max_retries: 3,
    usage_tracking_enabled: true,
    version: 1,
  })

  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/platform/model-configuration')
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/platform/model-configuration')
  expect(requestInit(fetchMock, 1)).toMatchObject({
    method: 'PATCH',
    body: JSON.stringify({
      timeout_seconds: 60,
      max_retries: 3,
      usage_tracking_enabled: true,
      version: 1,
    }),
  })

  const error = new ApiError(
    503,
    {
      error: {
        code: 'MODEL_ENVIRONMENT_NOT_CONFIGURED',
        message: '模型环境配置尚未完成。',
        request_id: 'req_test',
      },
    },
  )
  expect(isOrganizationApiError(error, 'MODEL_ENVIRONMENT_NOT_CONFIGURED')).toBe(true)
  expect(isOrganizationApiError(error, 'RESOURCE_VERSION_CONFLICT')).toBe(false)
})

test('uses Phase 4 member and support access contract routes', async () => {
  setCsrfToken('csrf-phase4')
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ items: [], next_cursor: null, has_more: false }))),
    )

  await listOrganizationMembers('org/1', {
    q: 'legal team',
    role: 'reviewer',
    status: 'active',
    sort: 'display_name',
    direction: 'asc',
    limit: 20,
    cursor: 'next cursor',
  })
  await inviteOrganizationMember('org/1', { email: 'member@example.com', role: 'viewer' }, 'invite-1')
  await resendOrganizationInvitation('member/1', 'resend-1')
  await updateOrganizationMember('member/1', { status: 'disabled', version: 3 })
  await listSupportAccessGrants('org/1', { status: 'active', limit: 20 })
  await createSupportAccessGrant(
    'org/1',
    {
      platform_admin_user_id: 'platform-1',
      reason: '排查问题',
      expires_at: '2026-08-19T10:00:00Z',
    },
    'grant-1',
  )
  await revokeSupportAccessGrant('org/1', 'grant/1')

  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    '/api/v1/organizations/org%2F1/members?q=legal+team&role=reviewer&status=active&sort=display_name&direction=asc&limit=20&cursor=next+cursor',
    '/api/v1/organizations/org%2F1/members',
    '/api/v1/members/member%2F1/resend-invitation',
    '/api/v1/members/member%2F1',
    '/api/v1/organizations/org%2F1/support-access-grants?status=active&limit=20',
    '/api/v1/organizations/org%2F1/support-access-grants',
    '/api/v1/organizations/org%2F1/support-access-grants/grant%2F1',
  ])
  expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(
    JSON.stringify({ email: 'member@example.com', role: 'viewer' }),
  )
  expect(fetchMock.mock.calls[5]?.[1]?.body).toBe(
    JSON.stringify({
      platform_admin_user_id: 'platform-1',
      reason: '排查问题',
      expires_at: '2026-08-19T10:00:00Z',
    }),
  )
  expect(new Headers(fetchMock.mock.calls[5]?.[1]?.headers).get('Idempotency-Key')).toBe('grant-1')
  expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('X-CSRF-Token')).toBe('csrf-phase4')
})
