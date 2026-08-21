import { expect, test, type Page } from '@playwright/test'

const reviewerSession = {
  user: {
    id: 'reviewer-1',
    email: 'reviewer@example.com',
    display_name: '审核员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'reviewer',
    status: 'active',
  }],
  csrf_token: 'csrf-phase12',
}

const task = {
  id: 'task-1',
  display_no: 'REV-20260820-000001',
  contract_id: 'contract-1',
  contract_file_id: 'file-1',
  document_version_id: 'document-1',
  status: 'pending_review',
  progress: 100,
  current_stage: 'report',
  rule_bundle_version_id: 'rule-version-1',
  clause_template_version_id: 'template-version-1',
  business_scenario: 'standard',
  error_code: null,
  error_message: null,
  created_at: '2026-08-20T00:00:00Z',
  started_at: '2026-08-20T00:00:00Z',
  finished_at: '2026-08-20T00:01:00Z',
  completed_by: null,
  completed_at: null,
}

const locator = {
  source_span_id: 'span-1',
  document_version_id: 'document-1',
  kind: 'pdf_page',
  page_no: 3,
  paragraph_no: null,
  table_path: null,
  start_offset: 0,
  end_offset: 8,
  bbox: null,
  quote: '责任条款未设置上限',
}

const baseResult = {
  review_task_id: 'task-1',
  classification: {
    id: 'classification-1',
    model_value: 'purchase',
    current_value: 'purchase',
    confidence: 0.96,
    status: 'detected',
    evidence: [locator],
    version: 1,
    edited_by: null,
    edited_at: null,
  },
  extracted_fields: ['parties', 'signing_date', 'contract_amount', 'performance_period', 'dispute_resolution', 'payment_terms', 'auto_renewal'].map((field_key) => ({
    id: `field-${field_key}`,
    field_key,
    model_value: null,
    current_value: null,
    status: 'not_found',
    confidence: 0.8,
    evidence: [],
    version: 1,
    edited_by: null,
    edited_at: null,
  })),
  risk_findings: [{
    id: 'finding-1',
    risk_type: 'unlimited_liability',
    severity: 'high',
    title: '责任范围不封顶',
    description: '责任条款没有设置合同金额上限。',
    basis: '责任条款未设置上限。',
    suggestion: '建议约定责任上限。',
    confidence: 0.88,
    source: 'model',
    status: 'pending_review',
    evidence: [locator],
    version: 1,
    edited_by: null,
    edited_at: null,
  }],
  clause_comparisons: [],
  summary: { risk_total: 1, high: 1, medium: 0, low: 0, warning_total: 1, unresolved_count: 1, required_manual_count: 1 },
  completion_blockers: [{ subject_type: 'risk_finding', subject_id: 'finding-1', code: 'RISK_PENDING_REVIEW', status: 'pending_review', version: 1 }],
}

async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: reviewerSession }))
}

async function mockEvidenceDocument(page: Page): Promise<void> {
  await page.route('**/api/v1/documents/document-1/pages/3*', (route) => route.fulfill({
    status: 200,
    json: {
      document_version_id: 'document-1',
      document_kind: 'pdf',
      page_no: 3,
      page_count: 3,
      width: 600,
      height: 800,
      text: '责任条款未设置上限',
      image_file_id: null,
      ocr_status: 'not_required',
      ocr_confidence: null,
      error_code: null,
      error_message: null,
      blocks: [{
        id: 'block-1',
        order_no: 1,
        block_type: 'paragraph',
        page_no: 3,
        paragraph_no: null,
        table_path: null,
        text: '责任条款未设置上限',
        bbox: null,
        source_spans: [locator],
      }],
    },
  }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('REVIEW-003 exposes blockers and supports evidence navigation at desktop widths', async ({ page }) => {
  await mockSession(page)
  await mockEvidenceDocument(page)
  await page.route('**/api/v1/review-tasks/task-1', (route) => route.fulfill({ status: 200, json: task }))
  await page.route('**/api/v1/review-tasks/task-1/results*', (route) => route.fulfill({ status: 200, json: baseResult }))

  await page.goto('/reviews/task-1/results')
  await expect(page.getByRole('heading', { name: '审核结果与人工复核' })).toBeVisible()
  await expect(page.getByText('完成审核前必须处理')).toBeVisible()
  await expect(page.getByText('RISK_PENDING_REVIEW')).toBeVisible()
  await page.getByRole('button', { name: '查看证据位置' }).click()
  await expect(page).toHaveURL(/\/documents\/document-1\?source_span_id=span-1&page=3$/)
  await assertNoHorizontalOverflow(page)
})

test('ADMIN-003 renders only contract-defined feedback aggregates', async ({ page }) => {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({
    status: 200,
    json: { ...reviewerSession, memberships: [{ ...reviewerSession.memberships[0], role: 'org_admin' }] },
  }))
  await page.route('**/api/v1/feedback/summary', (route) => route.fulfill({
    status: 200,
    json: {
      filters: { contract_type: null, rule_bundle_version_id: null, model_version: null, created_from: null, created_to: null },
      counts: { correct: 2, incorrect: 1, modified: 3, ignored: 0 },
      by_risk_type: [{ risk_type: 'purchase_keyword', correct: 1, incorrect: 1, modified: 2, ignored: 0 }],
    },
  }))

  await page.goto('/feedback/summary')
  await expect(page.getByRole('heading', { name: '反馈统计' })).toBeVisible()
  await expect(page.getByText('purchase_keyword')).toBeVisible()
  await expect(page.getByText('AI 得分')).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
})
