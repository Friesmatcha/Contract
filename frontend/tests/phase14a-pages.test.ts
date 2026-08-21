import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import AuditLogPage from '@/pages/audit/AuditLogPage.vue'
import OperationsMetricsPage from '@/pages/operations/OperationsMetricsPage.vue'
import { selectCurrentOrganization, sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  sessionState.current = null
  sessionState.loaded = false
  localStorage.clear()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function renderMetricsPage(path = '/organizations/org-1/metrics') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/organizations/:organizationId/metrics', component: OperationsMetricsPage }],
  })
  await router.push(path)
  await router.isReady()
  return render(OperationsMetricsPage, { global: { plugins: [router, ElementPlus] } })
}

const adminSession = {
  user: {
    id: 'admin-1',
    email: 'admin@example.com',
    display_name: '管理员',
    status: 'active' as const,
    is_platform_admin: false,
  },
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'org_admin' as const,
    status: 'active' as const,
  }],
  csrf_token: 'csrf-admin',
}

const auditPage = {
  items: [{
    id: 'audit-1',
    organization_id: 'org-1',
    action: 'review_task.completed',
    resource_type: 'review_task',
    resource_id: 'task-1',
    actor_id: 'admin-1',
    request_id: 'req-audit-1',
    before_summary: { status: 'pending_review' },
    after_summary: { status: 'completed' },
    created_at: '2026-08-21T00:00:00Z',
  }],
  next_cursor: null,
  has_more: false,
}

test('ADMIN-001 sends the trusted organization header and renders safe audit summaries', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  selectCurrentOrganization('org-1')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => response(auditPage))

  render(AuditLogPage, {
    props: { scope: 'organization' },
    global: { plugins: [ElementPlus] },
  })

  await waitFor(() => expect(screen.getByText('review_task.completed')).toBeInTheDocument())
  const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
  expect(new Headers(init?.headers).get('X-Organization-ID')).toBe('org-1')
  await fireEvent.update(screen.getByLabelText('动作'), 'warning_event')
  await fireEvent.click(screen.getByRole('button', { name: '筛选' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('action=warning_event')

  await fireEvent.click(screen.getByRole('button', { name: '查看安全摘要' }))
  expect(screen.getByText('变更后摘要')).toBeInTheDocument()
  expect(screen.getByText(/"status": "completed"/)).toBeInTheDocument()
})

test('PLATFORM-004 renders a safe forbidden state', async () => {
  sessionState.current = {
    ...adminSession,
    user: { ...adminSession.user, is_platform_admin: false },
    memberships: [{ ...adminSession.memberships[0]!, role: 'reviewer' as const }],
  }
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ error: { code: 'PLATFORM_ADMIN_REQUIRED', message: '仅平台管理员可查看审计日志。', request_id: 'req-platform' } }, 403),
  )

  render(AuditLogPage, {
    props: { scope: 'platform' },
    global: { plugins: [ElementPlus] },
  })

  await waitFor(() => expect(screen.getByText('无法查看平台审计')).toBeInTheDocument())
  expect(screen.getByText('请求 ID：req-platform')).toBeInTheDocument()
  expect(screen.queryByText('review_task.completed')).not.toBeInTheDocument()
})

test('ADMIN-002 renders contract-defined review and warning metrics', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  selectCurrentOrganization('org-1')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/metrics/reviews')) {
      return response({
        from: '2026-08-01T00:00:00Z',
        to: '2026-08-21T00:00:00Z',
        review_count: 12,
        completed_count: 9,
        failed_count: 1,
        average_duration_ms: 4200,
        parse_failure_rate: 0.1,
        model_failure_rate: 0.2,
        manual_edit_rate: 0.3,
      })
    }
    return response({
      from: '2026-08-01T00:00:00Z',
      to: '2026-08-21T00:00:00Z',
      created_count: 8,
      unprocessed_count: 2,
      closed_count: 5,
      closure_rate: 0.625,
      false_positive_rate: 0.125,
      average_unprocessed_duration_ms: 86_400_000,
      by_risk_type: [{ risk_type: 'unlimited_liability', count: 4 }],
    })
  })

  await renderMetricsPage()

  await waitFor(() => expect(screen.getByText('unlimited_liability')).toBeInTheDocument())
  expect(screen.getByText('12')).toBeInTheDocument()
  expect(screen.getByText('30.0%')).toBeInTheDocument()
  await fireEvent.update(screen.getByLabelText('风险类型'), 'payment_terms')
  await fireEvent.click(screen.getByRole('button', { name: '查询' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
  expect(String(fetchMock.mock.calls[3]?.[0])).toContain('risk_type=payment_terms')
})

test('ADMIN-002 presents 501 as a disabled capability state', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  selectCurrentOrganization('org-1')
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ error: { code: 'METRICS_NOT_ENABLED', message: '运营指标尚未启用。', request_id: 'req-metrics' } }, 501),
  )

  await renderMetricsPage()

  await waitFor(() => expect(screen.getAllByText('运营指标尚未启用。').length).toBeGreaterThan(0))
  expect(screen.getByText('ADMIN-002')).toBeInTheDocument()
  expect(screen.queryByText('系统错误')).not.toBeInTheDocument()
})

test('ADMIN-002 uses the organization in the route for multi-organization users', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [
      adminSession.memberships[0]!,
      { ...adminSession.memberships[0]!, organization_id: 'org-2', organization_name: '第二企业' },
    ],
  }
  sessionState.loaded = true
  selectCurrentOrganization('org-1')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => response({
    from: '2026-08-01T00:00:00Z',
    to: '2026-08-21T00:00:00Z',
    review_count: 0,
    completed_count: 0,
    failed_count: 0,
    average_duration_ms: 0,
    parse_failure_rate: 0,
    model_failure_rate: 0,
    manual_edit_rate: 0,
    created_count: 0,
    unprocessed_count: 0,
    closed_count: 0,
    closure_rate: 0,
    false_positive_rate: 0,
    average_unprocessed_duration_ms: 0,
    by_risk_type: [],
  }))

  await renderMetricsPage('/organizations/org-2/metrics')
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/organizations/org-2/metrics/')
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/organizations/org-2/metrics/')
})
