import { afterEach, expect, test, vi } from 'vitest'

import {
  createRiskRuleBundle,
  getRiskRuleBundle,
  listRiskRuleBundles,
  publishRiskRuleVersion,
  updateRiskRuleBundle,
} from '@/api/riskRules'
import { setCsrfToken } from '@/features/auth/csrf'

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => {
  setCsrfToken(null)
  vi.restoreAllMocks()
})

test('lists risk bundles with tenant scope and filters', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ items: [], next_cursor: null, has_more: false }),
  )

  await listRiskRuleBundles('org-1', { q: '付款', status: 'active', limit: 20 })

  expect(fetchMock.mock.calls[0]?.[0]).toBe(
    '/api/v1/risk-rule-bundles?q=%E4%BB%98%E6%AC%BE&status=active&limit=20',
  )
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('maps bundle creation, default switch and include-rules detail requests', async () => {
  setCsrfToken('csrf-risk')
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ id: 'bundle-1' }, 201))
    .mockResolvedValueOnce(response({ id: 'bundle-1', is_default: true, version: 2 }))
    .mockResolvedValueOnce(response({ id: 'bundle-1', versions: [] }))
    .mockResolvedValueOnce(response({ status: 'published' }))

  await createRiskRuleBundle('org-1', { name: '付款规则' }, 'risk-create-1')
  await updateRiskRuleBundle('bundle-1', { is_default: true, version: 1 })
  await getRiskRuleBundle('bundle-1', true)
  await publishRiskRuleVersion('version-1')

  const createHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers)
  expect(createHeaders.get('Idempotency-Key')).toBe('risk-create-1')
  expect(createHeaders.get('X-CSRF-Token')).toBe('csrf-risk')
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-Organization-ID')).toBeNull()
  expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/risk-rule-bundles/bundle-1?include_rules=true')
  expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('X-Organization-ID')).toBeNull()
  expect(JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body))).toEqual({})
  expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get('X-Organization-ID')).toBeNull()
})
