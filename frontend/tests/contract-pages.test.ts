import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import ContractListPage from '@/pages/contracts/ContractListPage.vue'
import CreateContractPage from '@/pages/contracts/CreateContractPage.vue'
import type { AuthSession } from '@/api/types'
import { selectCurrentOrganization, sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  sessionState.current = null
  sessionState.loaded = false
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function renderAt(component: object, path: string, routes: Array<{ path: string; component: object }>) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return render(component, { global: { plugins: [router, ElementPlus] } })
}

const currentSession: AuthSession = {
  user: {
    id: 'user-1',
    email: 'reviewer@example.com',
    display_name: '审核员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [
    {
      organization_id: 'org-1',
      organization_name: '示例企业',
      role: 'reviewer',
      status: 'active',
    },
  ],
  csrf_token: 'csrf-contract',
}

test('contract list loads rows and sends the current organization header', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      items: [
        {
          id: 'contract-1',
          display_no: 'CTR-20260819-000001',
          title: '供应商采购合同',
          declared_type: 'purchase',
          status: 'active',
          owner_id: 'user-1',
          current_file: null,
          files: [],
          latest_review: null,
          created_at: '2026-08-19T06:00:00Z',
          updated_at: '2026-08-19T06:00:00Z',
          version: 1,
        },
      ],
      next_cursor: null,
      has_more: false,
    }),
  )

  await renderAt(ContractListPage, '/contracts', [{ path: '/contracts', component: ContractListPage }])

  await waitFor(() => expect(screen.getByText('供应商采购合同')).toBeInTheDocument())
  expect(screen.getAllByText('采购').length).toBeGreaterThan(0)
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('contract list ignores a late response from the previous organization', async () => {
  sessionState.current = {
    ...currentSession,
    memberships: [
      currentSession.memberships[0]!,
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'reviewer',
        status: 'active',
      },
    ],
  }
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-1')).toBe(true)
  let resolveFirst: (value: Response) => void = () => undefined
  const firstResponse = new Promise<Response>((resolve) => {
    resolveFirst = resolve
  })
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementationOnce(() => firstResponse)
    .mockResolvedValueOnce(
      response({
        items: [
          {
            id: 'contract-2',
            display_no: 'CTR-ORG2-000001',
            title: '第二组织合同',
            declared_type: 'sales',
            status: 'active',
            owner_id: 'user-1',
            current_file: null,
            files: [],
            latest_review: null,
            created_at: '2026-08-19T06:00:00Z',
            updated_at: '2026-08-19T06:00:00Z',
            version: 1,
          },
        ],
        next_cursor: null,
        has_more: false,
      }),
    )

  await renderAt(ContractListPage, '/contracts', [{ path: '/contracts', component: ContractListPage }])
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(selectCurrentOrganization('org-2')).toBe(true)
  await waitFor(() => expect(screen.getByText('第二组织合同')).toBeInTheDocument())

  resolveFirst(
    response({
      items: [
        {
          id: 'contract-1',
          display_no: 'CTR-ORG1-000001',
          title: '第一组织旧响应',
          declared_type: 'purchase',
          status: 'active',
          owner_id: 'user-1',
          current_file: null,
          files: [],
          latest_review: null,
          created_at: '2026-08-19T06:00:00Z',
          updated_at: '2026-08-19T06:00:00Z',
          version: 1,
        },
      ],
      next_cursor: null,
      has_more: false,
    }),
  )
  await waitFor(() => expect(screen.queryByText('第一组织旧响应')).not.toBeInTheDocument())
})

test('create contract validates a title and sends idempotency key', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ id: 'contract-1' }, 201),
  )
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000001')

  await renderAt(CreateContractPage, '/contracts/new', [
    { path: '/contracts/new', component: CreateContractPage },
  ])
  await fireEvent.update(screen.getByRole('textbox', { name: '合同名称' }), '新采购合同')
  await fireEvent.click(screen.getByRole('button', { name: '创建合同' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/contracts')
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Idempotency-Key')).toBe(
    '00000000-0000-4000-8000-000000000001',
  )
  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
    title: '新采购合同',
  })
})
