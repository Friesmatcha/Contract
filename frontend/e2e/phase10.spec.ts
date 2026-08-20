import { expect, test, type Page } from '@playwright/test'

const session = {
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
  csrf_token: 'csrf-phase10',
}

const task = {
  id: 'task-1',
  display_no: 'REV-20260820-000001',
  contract_id: 'contract-1',
  contract_file_id: 'file-1',
  document_version_id: 'document-1',
  status: 'completed',
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

const fields = [
  'parties',
  'signing_date',
  'contract_amount',
  'performance_period',
  'dispute_resolution',
  'payment_terms',
  'auto_renewal',
].map((field_key) => ({
  id: `field-${field_key}`,
  field_key,
  model_value: field_key === 'auto_renewal' ? null : field_key,
  current_value: field_key === 'auto_renewal' ? null : field_key,
  status: field_key === 'auto_renewal' ? 'not_found' : 'detected',
  confidence: 0.8,
  evidence: field_key === 'auto_renewal' ? [] : [locator],
  version: 1,
}))

const results = {
  review_task_id: 'task-1',
  classification: {
    id: 'classification-1',
    model_value: 'purchase',
    current_value: 'purchase',
    confidence: 0.96,
    status: 'detected',
    evidence: [locator],
    version: 1,
  },
  extracted_fields: fields,
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
  }],
  clause_comparisons: [{
    id: 'comparison-1',
    clause_key: 'payment',
    status: 'deviated',
    contract_text: '验收后付款',
    difference_summary: '缺少付款期限。',
    severity: 'medium',
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

async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: session }))
  await page.route('**/api/v1/review-tasks/task-1', (route) => route.fulfill({ status: 200, json: task }))
  await page.route('**/api/v1/review-tasks/task-1/results*', (route) => route.fulfill({ status: 200, json: results }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('REVIEW-003 shows the aggregated result workspace at desktop widths', async ({ page }) => {
  await mockSession(page)
  await page.goto('/reviews/task-1/results')

  await expect(page.getByRole('heading', { name: '审核结果与人工复核' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '风险发现' })).toBeVisible()
  await expect(page.getByText('责任范围不封顶')).toBeVisible()
  await expect(page.getByRole('heading', { name: '条款对照' })).toBeVisible()
  await expect(page.locator('table.clause-result-table').getByText('存在偏差')).toBeVisible()
  await assertNoHorizontalOverflow(page)
})
