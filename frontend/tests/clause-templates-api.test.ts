import { afterEach, expect, test, vi } from 'vitest'

import {
  createClauseTemplate,
  createClauseTemplateVersion,
  getClauseTemplate,
  getClauseTemplateVersion,
  listClauseTemplates,
  publishClauseTemplateVersion,
  updateClauseTemplate,
  updateClauseTemplateVersion,
} from '@/api/clauseTemplates'
import { setCsrfToken } from '@/features/auth/csrf'

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => {
  setCsrfToken(null)
  vi.restoreAllMocks()
})

test('lists clause templates with tenant scope and exact filters', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ items: [], next_cursor: null, has_more: false }),
  )

  await listClauseTemplates('org-1', {
    q: '采购',
    contract_type: 'purchase',
    business_scenario: 'standard',
    status: 'active',
  })

  expect(fetchMock.mock.calls[0]?.[0]).toBe(
    '/api/v1/clause-templates?q=%E9%87%87%E8%B4%AD&contract_type=purchase&business_scenario=standard&status=active',
  )
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('maps clause template create, detail, version editing and publish routes', async () => {
  setCsrfToken('csrf-clause')
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ id: 'template-1' }, 201))
    .mockResolvedValueOnce(response({ id: 'template-1', versions: [] }))
    .mockResolvedValueOnce(response({ id: 'template-1', version: 2 }))
    .mockResolvedValueOnce(response({ id: 'version-1' }, 201))
    .mockResolvedValueOnce(response({ id: 'version-1' }))
    .mockResolvedValueOnce(response({ id: 'version-1', version: 2 }))
    .mockResolvedValueOnce(response({ id: 'version-1', status: 'published' }))

  await createClauseTemplate('org-1', { name: '采购基线', contract_type: 'purchase' }, 'clause-create-1')
  await getClauseTemplate('template-1', true)
  await updateClauseTemplate('template-1', { is_default: true, version: 1 })
  await createClauseTemplateVersion('template-1', { change_note: '初始化', clauses: [] }, 'clause-version-1')
  await getClauseTemplateVersion('version-1')
  await updateClauseTemplateVersion('version-1', { change_note: '修订', version: 1 })
  await publishClauseTemplateVersion('version-1')

  const createHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers)
  expect(createHeaders.get('X-Organization-ID')).toBe('org-1')
  expect(createHeaders.get('Idempotency-Key')).toBe('clause-create-1')
  expect(createHeaders.get('X-CSRF-Token')).toBe('csrf-clause')
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/clause-templates/template-1?include_clauses=true')
  expect(fetchMock.mock.calls[3]?.[0]).toBe('/api/v1/clause-templates/template-1/versions')
  expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get('Idempotency-Key')).toBe('clause-version-1')
  expect(fetchMock.mock.calls[6]?.[0]).toBe('/api/v1/clause-template-versions/version-1/publish')
  expect(JSON.parse(String(fetchMock.mock.calls[6]?.[1]?.body))).toEqual({})
})
