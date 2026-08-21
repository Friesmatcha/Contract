import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import { getReviewResults } from '@/api/reviews'
import { sessionState } from '@/features/auth/session'
import ReviewResultsPage from '@/pages/reviews/ReviewResultsPage.vue'

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

const task = {
  id: 'task-1',
  display_no: 'REV-20260820-000001',
  contract_id: 'contract-1',
  contract_file_id: 'file-1',
  document_version_id: 'document-1',
  status: 'completed' as const,
  progress: 100,
  current_stage: 'report' as const,
  rule_bundle_version_id: 'rule-version-1',
  clause_template_version_id: 'template-version-1',
  business_scenario: 'standard',
  error_code: null,
  error_message: null,
  created_at: '2026-08-20T00:00:00Z',
  started_at: '2026-08-20T00:00:00Z',
  finished_at: '2026-08-20T00:01:00Z',
}

const locator = {
  source_span_id: 'span-1',
  document_version_id: 'document-1',
  kind: 'pdf_page' as const,
  page_no: 3,
  paragraph_no: null,
  table_path: null,
  start_offset: 0,
  end_offset: 4,
  bbox: null,
  quote: '责任条款未设置上限',
}

const result = {
  review_task_id: 'task-1',
  classification: {
    id: 'classification-1',
    model_value: 'purchase' as const,
    current_value: 'purchase' as const,
    confidence: 0.96,
    status: 'detected' as const,
    evidence: [locator],
    version: 1,
  },
  extracted_fields: [
    'parties',
    'signing_date',
    'contract_amount',
    'performance_period',
    'dispute_resolution',
    'payment_terms',
    'auto_renewal',
  ].map((field_key) => ({
    id: `field-${field_key}`,
    field_key: field_key as 'parties',
    model_value: field_key === 'auto_renewal' ? null : field_key,
    current_value: field_key === 'auto_renewal' ? null : field_key,
    status: field_key === 'auto_renewal' ? 'not_found' as const : 'detected' as const,
    confidence: 0.8,
    evidence: field_key === 'auto_renewal' ? [] : [locator],
    version: 1,
  })),
  risk_findings: [{
    id: 'finding-1',
    risk_type: 'unlimited_liability',
    severity: 'high' as const,
    title: '责任范围不封顶',
    description: '责任条款没有设置合同金额上限。',
    basis: '责任条款未设置上限。',
    suggestion: '建议约定责任上限。',
    confidence: 0.88,
    source: 'model' as const,
    status: 'pending_review' as const,
    evidence: [locator],
    version: 1,
  }],
  clause_comparisons: [{
    id: 'comparison-1',
    clause_key: 'payment',
    status: 'deviated' as const,
    contract_text: '验收后付款',
    difference_summary: '缺少付款期限。',
    severity: 'medium' as const,
    suggestion: '补充付款期限。',
    evidence: [locator],
    version: 1,
  }],
  summary: {
    risk_total: 1,
    high: 1,
    medium: 0,
    low: 0,
    warning_total: 0,
    unresolved_count: 2,
  },
}

async function renderPage(path = '/reviews/task-1/results') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reviews/:reviewTaskId/results', component: ReviewResultsPage },
      { path: '/documents/:documentVersionId', component: { template: '<div>document</div>' } },
      { path: '/reviews/:reviewTaskId', component: { template: '<div>progress</div>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  return { router, ...render(ReviewResultsPage, { global: { plugins: [router, ElementPlus] } }) }
}

test('review result API sends only contract-defined filters', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(result))

  await getReviewResults('task/1', {
    riskSeverity: 'high',
    riskStatus: 'pending_review',
    clauseStatus: 'deviated',
  })

  expect(fetchMock.mock.calls[0]?.[0]).toBe(
    '/api/v1/review-tasks/task%2F1/results?include_evidence=true&risk_severity=high&risk_status=pending_review&clause_status=deviated',
  )
})

test('REVIEW-003 renders risk, clause, summary and evidence navigation read-only', async () => {
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(task))
    .mockResolvedValueOnce(response(result))

  const { router } = await renderPage()

  await waitFor(() => expect(screen.getByRole('heading', { name: '风险发现' })).toBeInTheDocument())
  expect(screen.getByText('责任范围不封顶')).toBeInTheDocument()
  expect(screen.getAllByText('存在偏差').length).toBeGreaterThan(0)
  expect(screen.getByText('待处理')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument()

  await fireEvent.click(screen.getAllByRole('button', { name: '第 3 页' })[0]!)
  await waitFor(() => expect(router.currentRoute.value.path).toBe('/documents/document-1'))
  expect(router.currentRoute.value.query.source_span_id).toBe('span-1')
})

test('REVIEW-003 separates results-not-ready from a completed result error', async () => {
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ ...task, status: 'reviewing', current_stage: 'risk_analysis' }))
    .mockResolvedValueOnce(response({ error: { code: 'RESULTS_NOT_READY', message: '结果尚未完成。', request_id: 'req-1' } }, 409))

  await renderPage()

  await waitFor(() => expect(screen.getByText('结果仍在处理中')).toBeInTheDocument())
  expect(screen.getByText('查看进度')).toBeInTheDocument()
  expect(screen.queryByText('风险发现')).not.toBeInTheDocument()
})

test('REVIEW-003 shows a safe forbidden state without exposing result data', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    response({ error: { code: 'REVIEW_TASK_NOT_FOUND', message: '审核任务不存在。', request_id: 'req-404' } }, 404),
  )

  await renderPage()

  await waitFor(() => expect(screen.getByText('无法访问审核结果')).toBeInTheDocument())
  expect(screen.getByText('请求 ID：req-404')).toBeInTheDocument()
  expect(screen.queryByText('责任范围不封顶')).not.toBeInTheDocument()
})

const reviewerSession = {
  user: {
    id: 'reviewer-1',
    email: 'reviewer@example.com',
    display_name: '审核员',
    status: 'active' as const,
    is_platform_admin: false,
  },
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'reviewer' as const,
    status: 'active' as const,
  }],
  csrf_token: 'csrf-phase12',
}

const pendingTask = { ...task, status: 'pending_review' as const }
const blockedResult = {
  ...result,
  summary: { ...result.summary, required_manual_count: 1 },
  completion_blockers: [{
    subject_type: 'risk_finding' as const,
    subject_id: 'finding-1',
    code: 'RISK_PENDING_REVIEW',
    status: 'pending_review',
    version: 1,
  }],
}

test('REVIEW-003 keeps an edit conflict visible and refreshes the server state', async () => {
  sessionState.current = reviewerSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(pendingTask))
    .mockResolvedValueOnce(response(blockedResult))
    .mockResolvedValueOnce(response({ error: { code: 'RESOURCE_VERSION_CONFLICT', message: '结果已更新。', request_id: 'req-conflict' } }, 409))
    .mockResolvedValueOnce(response(pendingTask))
    .mockResolvedValueOnce(response(blockedResult))

  await renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: '编辑分类' })).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '编辑分类' }))
  await fireEvent.click(screen.getByRole('button', { name: '保存修订' }))

  await waitFor(() => expect(screen.getByText('结果已被其他审核员更新，已刷新服务器版本。请重新打开编辑。')).toBeInTheDocument())
  expect(screen.queryByText('请求 ID：req-conflict')).not.toBeInTheDocument()
})

test('REVIEW-003 displays server completion blockers after a rejected completion', async () => {
  sessionState.current = reviewerSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(pendingTask))
    .mockResolvedValueOnce(response(blockedResult))
    .mockResolvedValueOnce(response({ error: { code: 'UNRESOLVED_REQUIRED_FINDINGS', message: '仍有必须人工处理的审核结果。', request_id: 'req-blocked' } }, 409))
    .mockResolvedValueOnce(response(blockedResult))

  await renderPage()
  await waitFor(() => expect(screen.getByRole('button', { name: '完成审核' })).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '完成审核' }))

  await waitFor(() => expect(screen.getByText('审核尚未完成')).toBeInTheDocument())
  expect(screen.getByText('RISK_PENDING_REVIEW')).toBeInTheDocument()
  expect(screen.getByText('完成审核前必须处理')).toBeInTheDocument()
})

test('REVIEW-003 keeps viewer actions read-only', async () => {
  sessionState.current = {
    ...reviewerSession,
    user: { ...reviewerSession.user, id: 'viewer-1', display_name: '查看者' },
    memberships: [{ ...reviewerSession.memberships[0]!, role: 'viewer' as const }],
  }
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(task))
    .mockResolvedValueOnce(response(result))

  await renderPage()
  await waitFor(() => expect(screen.getByRole('heading', { name: '风险发现' })).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /反馈/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '完成审核' })).not.toBeInTheDocument()
})
