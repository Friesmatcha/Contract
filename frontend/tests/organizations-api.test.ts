import { setCsrfToken } from '@/features/auth/csrf'
import {
  createPlatformOrganization,
  getOrganizationProfile,
  getOrganizationSettings,
  getPlatformModelConfiguration,
  getPlatformOrganization,
  isOrganizationApiError,
  listPlatformOrganizations,
  updateOrganizationSettings,
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
