import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import OrganizationMembersPage from '@/pages/organization/OrganizationMembersPage.vue'
import SupportAccessPage from '@/pages/organization/SupportAccessPage.vue'

afterEach(() => {
  cleanup()
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

const pendingMember = {
  id: 'member-1',
  user_id: null,
  email: 'reviewer@example.com',
  display_name: null,
  role: 'reviewer',
  status: 'pending_invitation',
  invited_at: '2026-08-19T04:00:00Z',
  email_delivery_status: 'sent',
  version: 1,
  created_at: '2026-08-19T04:00:00Z',
  updated_at: '2026-08-19T04:00:00Z',
}

test('member page loads members and submits an invitation with a fresh idempotency key', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ items: [pendingMember], next_cursor: null, has_more: false }))
    .mockResolvedValueOnce(response(pendingMember, 201))
    .mockResolvedValueOnce(response({ items: [pendingMember], next_cursor: null, has_more: false }))

  await renderAt(OrganizationMembersPage, '/organizations/org-1/members', [
    { path: '/organizations/:organizationId/members', component: OrganizationMembersPage },
  ])

  await waitFor(() => expect(screen.getByText('reviewer@example.com')).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '邀请成员' }))
  await fireEvent.update(screen.getByRole('textbox', { name: '成员邮箱' }), 'new-user@example.com')
  await fireEvent.click(screen.getByRole('button', { name: '发送邀请' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/organizations/org-1/members')
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
    email: 'new-user@example.com',
    role: 'reviewer',
  })
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('Idempotency-Key')).toBeTruthy()
})

test('support access page exposes the read-only boundary and empty state', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ items: [], next_cursor: null, has_more: false }),
  )

  await renderAt(SupportAccessPage, '/organizations/org-1/support-access-grants', [
    { path: '/organizations/:organizationId/support-access-grants', component: SupportAccessPage },
  ])

  await waitFor(() => expect(screen.getByText('暂无支持授权记录')).toBeInTheDocument())
  expect(screen.getByRole('heading', { name: '支持授权' })).toBeInTheDocument()
  expect(screen.getByText('只读支持访问，最长 4 小时，每次访问都会产生审计记录。')).toBeInTheDocument()
  expect(screen.getByText('暂无支持授权记录')).toBeInTheDocument()
})
