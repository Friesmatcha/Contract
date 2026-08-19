import { afterEach, expect, test, vi } from 'vitest'

import {
  archiveContract,
  createContract,
  getContract,
  grantContractAccess,
  listContracts,
  revokeContractAccess,
  restoreContract,
  updateContract,
} from '@/api/contracts'
import { setCsrfToken } from '@/features/auth/csrf'

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

afterEach(() => {
  vi.restoreAllMocks()
  setCsrfToken(null)
})

test('maps contract catalog queries and actions to the documented routes', async () => {
  setCsrfToken('csrf-contract')
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() => Promise.resolve(response({ items: [], next_cursor: null, has_more: false })))

  await listContracts('org/1', {
    q: '采购合同',
    owner_id: 'owner-1',
    status: 'active',
    declared_type: 'purchase',
    sort: 'title',
    direction: 'asc',
    limit: 20,
    cursor: 'next cursor',
  })
  await createContract('org/1', { title: '采购合同', declared_type: 'purchase' }, 'contract-1')
  await getContract('contract/1', 'org/1')
  await updateContract('contract/1', { title: '修订合同', version: 1 })
  await archiveContract('contract/1')
  await restoreContract('contract/1')
  await grantContractAccess('contract/1', 'viewer/1')
  await revokeContractAccess('contract/1', 'viewer/1')

  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    '/api/v1/contracts?q=%E9%87%87%E8%B4%AD%E5%90%88%E5%90%8C&owner_id=owner-1&status=active&declared_type=purchase&sort=title&direction=asc&limit=20&cursor=next+cursor',
    '/api/v1/contracts',
    '/api/v1/contracts/contract%2F1',
    '/api/v1/contracts/contract%2F1',
    '/api/v1/contracts/contract%2F1/archive',
    '/api/v1/contracts/contract%2F1/restore',
    '/api/v1/contracts/contract%2F1/access-grants/viewer%2F1',
    '/api/v1/contracts/contract%2F1/access-grants/viewer%2F1',
  ])
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org/1')
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('Idempotency-Key')).toBe('contract-1')
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-CSRF-Token')).toBe('csrf-contract')
})
