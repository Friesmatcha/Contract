import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import FeedbackSummaryPage from '@/pages/feedback/FeedbackSummaryPage.vue'
import { sessionState } from '@/features/auth/session'

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

const summary = {
  filters: {
    contract_type: null,
    rule_bundle_version_id: null,
    model_version: null,
    created_from: null,
    created_to: null,
  },
  counts: { correct: 2, incorrect: 1, modified: 3, ignored: 0 },
  by_risk_type: [{ risk_type: 'purchase_keyword', correct: 1, incorrect: 1, modified: 2, ignored: 0 }],
}

async function renderPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/feedback/summary', component: FeedbackSummaryPage }],
  })
  await router.push('/feedback/summary')
  await router.isReady()
  return render(FeedbackSummaryPage, { global: { plugins: [router, ElementPlus] } })
}

test('ADMIN-003 displays contract-defined filters and feedback counts', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(summary))

  await renderPage()
  await waitFor(() => expect(screen.getByLabelText('规则版本 ID')).toBeInTheDocument())
  expect(screen.getByText('purchase_keyword')).toBeInTheDocument()
  expect(screen.getByText('3')).toBeInTheDocument()

  await fireEvent.update(screen.getByLabelText('规则版本 ID'), 'rule-version-1')
  await fireEvent.click(screen.getByRole('button', { name: '筛选' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('rule_bundle_version_id=rule-version-1')
})

test('ADMIN-003 shows a safe forbidden state', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [{ ...adminSession.memberships[0]!, role: 'reviewer' as const }],
  }
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ error: { code: 'ORG_ADMIN_REQUIRED', message: '仅组织管理员可查看反馈统计。', request_id: 'req-feedback' } }, 403),
  )

  await renderPage()
  await waitFor(() => expect(screen.getByText('无法查看反馈统计')).toBeInTheDocument())
  expect(screen.getByText('请求 ID：req-feedback')).toBeInTheDocument()
  expect(screen.queryByText('purchase_keyword')).not.toBeInTheDocument()
})
