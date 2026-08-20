import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import NotificationDrawer from '@/components/NotificationDrawer.vue'
import WarningDetailPage from '@/pages/warnings/WarningDetailPage.vue'
import WarningListPage from '@/pages/warnings/WarningListPage.vue'
import { sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  sessionState.current = null
  sessionState.loaded = false
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const organizationId = 'org-1'
const warningId = 'warning-1'
const session = {
  user: {
    id: 'user-1',
    email: 'reviewer@example.test',
    display_name: '审核员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [{ organization_id: organizationId, organization_name: '测试组织', role: 'reviewer' as const, status: 'active' as const }],
  csrf_token: 'csrf-test',
}

const warning = {
  id: warningId,
  contract_id: 'contract-1',
  review_task_id: 'task-1',
  severity: 'high' as const,
  status: 'pending_confirmation' as const,
  priority: 'high' as const,
  assignee_id: null,
  due_at: null,
  trigger_type: 'high_risk',
  triggered_at: '2026-08-20T03:34:00Z',
}

const detail = {
  ...warning,
  risk_finding_id: 'finding-1',
  clause_comparison_id: null,
  extracted_field_id: null,
  classification_id: null,
  assignee: null,
  resolution: null,
  revision_id: null,
  closed_at: null,
  evidence: [{
    source_span_id: 'span-1',
    document_version_id: 'document-1',
    kind: 'pdf_page' as const,
    page_no: 3,
    paragraph_no: null,
    table_path: null,
    start_offset: 0,
    end_offset: 8,
    bbox: null,
    quote: '责任条款未设置上限',
  }],
  events: [{
    event_id: 'event-1',
    event_type: 'created',
    from_status: null,
    to_status: 'pending_confirmation' as const,
    actor_id: null,
    note: null,
    assignee_id: null,
    due_at: null,
    created_at: '2026-08-20T03:34:00Z',
  }],
}

function useSession(): void {
  sessionState.current = session
  sessionState.loaded = true
}

async function routerFor(path: string, routes: { path: string; component: object }[]) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return router
}

test('WARNING-001 loads warnings and opens WARNING-002', async () => {
  useSession()
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ items: [warning], next_cursor: null, has_more: false, summary: { unprocessed_count: 1, high_count: 1 } }),
  )
  const router = await routerFor('/warnings', [
    { path: '/warnings', component: WarningListPage },
    { path: '/warnings/:warningId', component: { template: '<div>detail</div>' } },
  ])

  render(WarningListPage, { global: { plugins: [router, ElementPlus] } })

  await waitFor(() => expect(screen.getByRole('button', { name: /查看/ })).toBeInTheDocument())
  expect(screen.getAllByText('高风险').length).toBeGreaterThan(0)
  expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/v1/warnings?')

  await fireEvent.click(screen.getByRole('button', { name: /查看/ }))
  await waitFor(() => expect(router.currentRoute.value.path).toBe(`/warnings/${warningId}`))
})

test('WARNING-002 submits a contract-defined assignment event', async () => {
  useSession()
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(detail))
    .mockResolvedValueOnce(response({ event_id: 'event-2', event_type: 'assign', from_status: 'pending_confirmation', to_status: 'pending_confirmation', actor_id: 'user-1', note: '请复核', assignee_id: 'user-1', due_at: null, created_at: '2026-08-20T03:35:00Z' }, 201))
    .mockResolvedValueOnce(response({ ...detail, assignee_id: 'user-1', assignee: { id: 'user-1', display_name: '审核员', email: 'reviewer@example.test' } }))
  const router = await routerFor(`/warnings/${warningId}`, [
    { path: '/warnings/:warningId', component: WarningDetailPage },
  ])

  render(WarningDetailPage, { global: { plugins: [router, ElementPlus] } })
  await waitFor(() => expect(screen.getByRole('heading', { name: '预警详情' })).toBeInTheDocument())

  await fireEvent.click(screen.getByRole('button', { name: '分派责任人' }))
  await fireEvent.update(screen.getByLabelText('责任人 ID'), 'user-1')
  await fireEvent.update(screen.getByLabelText('预警说明'), '请复核')
  await fireEvent.click(screen.getByRole('button', { name: '提交' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/v1/warnings/${warningId}/events`)
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
    type: 'assign',
    assignee_id: 'user-1',
    due_at: null,
    note: '请复核',
  })
})

test('NOTIFY-001 marks an unread notification read before navigation', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({
      items: [{ id: 'notification-1', warning_id: warningId, channel: 'in_app', status: 'unread', title: '发现高风险预警', body: '请前往预警中心复核。', created_at: '2026-08-20T03:34:05Z' }],
      next_cursor: null,
      has_more: false,
    }))
    .mockResolvedValueOnce(response({ unread_count: 1 }))
    .mockResolvedValueOnce(response({ id: 'notification-1', status: 'read', read_at: '2026-08-20T03:35:00Z' }))
    .mockResolvedValueOnce(response({ unread_count: 0 }))
  const router = await routerFor('/', [
    { path: '/', component: { template: '<div />' } },
    { path: '/warnings/:warningId', component: { template: '<div>detail</div>' } },
  ])

  render(NotificationDrawer, { props: { modelValue: true }, global: { plugins: [router, ElementPlus] } })
  await waitFor(() => expect(screen.getByText('发现高风险预警')).toBeInTheDocument())

  await fireEvent.click(screen.getByRole('button', { name: /发现高风险预警/ }))
  await waitFor(() => expect(router.currentRoute.value.path).toBe(`/warnings/${warningId}`))
  expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/notifications/notification-1/read')
})
