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
  csrf_token: 'csrf-review-9a',
}

const contract = {
  id: 'contract-1',
  display_no: 'CTR-20260820-000001',
  title: '采购审核合同',
  declared_type: 'purchase',
  status: 'active',
  owner_id: 'reviewer-1',
  current_file: {
    id: 'file-1',
    version_no: 1,
    is_current: true,
    original_name: '采购合同.pdf',
    scan_status: 'clean',
    storage_status: 'stored',
    external_model_notice_acknowledged_at: '2026-08-20T00:00:00Z',
  },
  files: [{
    id: 'file-1',
    version_no: 1,
    is_current: true,
    original_name: '采购合同.pdf',
    scan_status: 'clean',
    storage_status: 'stored',
    external_model_notice_acknowledged_at: '2026-08-20T00:00:00Z',
  }],
  latest_review: null,
  created_at: '2026-08-20T00:00:00Z',
  updated_at: '2026-08-20T00:00:00Z',
  version: 1,
}

const ruleBundle = {
  id: 'rule-bundle-1',
  name: '默认风险规则',
  status: 'active',
  current_published_version_id: 'rule-version-1',
  is_default: true,
}

const clauseTemplate = {
  id: 'clause-template-1',
  name: '采购条款模板',
  contract_type: 'purchase',
  business_scenario: 'standard',
  status: 'active',
  current_published_version_id: 'template-version-1',
  is_default: true,
}

const task = {
  id: 'task-1',
  display_no: 'REV-20260820-000001',
  contract_id: 'contract-1',
  contract_file_id: 'file-1',
  document_version_id: null,
  status: 'pending',
  progress: 0,
  current_stage: 'queued',
  rule_bundle_version_id: 'rule-version-1',
  clause_template_version_id: 'template-version-1',
  business_scenario: 'standard',
  error_code: null,
  error_message: null,
  created_at: '2026-08-20T00:00:00Z',
  started_at: null,
  finished_at: null,
  stage_runs: [],
}

async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: session }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('REVIEW-001 creates a pending review and opens REVIEW-002', async ({ page }) => {
  await mockSession(page)
  await page.route('**/api/v1/contracts/contract-1/reviews', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postDataJSON()).toEqual({
      contract_file_id: 'file-1',
      business_scenario: 'standard',
    })
    await route.fulfill({ status: 202, json: { ...task, status: 'pending' } })
  })
  await page.route('**/api/v1/contracts/contract-1', async (route) => {
    expect(route.request().method()).toBe('GET')
    await route.fulfill({ status: 200, json: contract })
  })
  await page.route('**/api/v1/risk-rule-bundles?*', (route) => route.fulfill({
    status: 200,
    json: { items: [ruleBundle], next_cursor: null, has_more: false },
  }))
  await page.route('**/api/v1/clause-templates?*', (route) => route.fulfill({
    status: 200,
    json: { items: [clauseTemplate], next_cursor: null, has_more: false },
  }))
  await page.route('**/api/v1/review-tasks/task-1*', (route) => route.fulfill({
    status: 200,
    json: { ...task, stage_runs: [] },
  }))

  await page.goto('/contracts/contract-1/reviews/new')
  await expect(page.getByRole('heading', { name: '创建审核任务' })).toBeVisible()
  await page.getByRole('button', { name: '创建审核任务' }).click()
  await expect(page).toHaveURL(/\/reviews\/task-1$/)
  await expect(page.getByRole('heading', { name: '等待处理' })).toBeVisible()
  await assertNoHorizontalOverflow(page)
})

test('CONTRACT-003 shows an active review and hides duplicate creation', async ({ page }) => {
  await mockSession(page)
  await page.route('**/api/v1/contracts/contract-1', (route) => route.fulfill({
    status: 200,
    json: {
      ...contract,
      latest_review: { id: 'task-1', status: 'reviewing' },
    },
  }))

  await page.goto('/contracts/contract-1')
  await expect(page.getByRole('heading', { name: '采购审核合同' })).toBeVisible()
  await expect(page.getByText('正在审核')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建审核' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '查看进度' })).toBeVisible()
  await assertNoHorizontalOverflow(page)
})

test('REVIEW-002 stops polling after a terminal task state', async ({ page }) => {
  await mockSession(page)
  let taskReads = 0
  const completedTask = {
    ...task,
    status: 'completed',
    progress: 100,
    current_stage: 'report',
    finished_at: '2026-08-20T00:05:00Z',
    stage_runs: [{
      id: 'stage-run-1',
      stage: 'report',
      status: 'succeeded',
      attempt_no: 1,
      heartbeat_at: '2026-08-20T00:05:00Z',
      started_at: '2026-08-20T00:04:00Z',
      finished_at: '2026-08-20T00:05:00Z',
      error_code: null,
      error_message: null,
    }],
  }
  await page.route('**/api/v1/review-tasks/task-1*', async (route) => {
    taskReads += 1
    await route.fulfill({ status: 200, json: completedTask })
  })
  await page.route('**/api/v1/contracts/contract-1**', (route) => route.fulfill({
    status: 200,
    json: contract,
  }))

  await page.goto('/reviews/task-1')
  await expect(page.getByRole('heading', { name: '审核已完成' })).toBeVisible()
  await page.waitForTimeout(2200)
  expect(taskReads).toBe(1)
  await expect(page.getByText('进入审核结果')).toBeEnabled()
  await assertNoHorizontalOverflow(page)
})

test('REVIEW-002 retries a failed task and returns it to pending', async ({ page }) => {
  await mockSession(page)
  const failedTask = {
    ...task,
    status: 'failed',
    progress: 17,
    current_stage: 'parsing',
    error_code: 'STAGE_EXECUTION_FAILED',
    error_message: '阶段执行失败，请重试。',
    stage_runs: [{
      id: 'stage-run-1',
      stage: 'parsing',
      status: 'failed',
      attempt_no: 1,
      heartbeat_at: null,
      started_at: '2026-08-20T00:00:00Z',
      finished_at: '2026-08-20T00:00:01Z',
      error_code: 'STAGE_EXECUTION_FAILED',
      error_message: '阶段执行失败，请重试。',
    }],
  }
  let retried = false
  await page.route('**/api/v1/review-tasks/task-1/retry', async (route) => {
    expect(route.request().method()).toBe('POST')
    retried = true
    await route.fulfill({ status: 202, json: { review_task_id: 'task-1', status: 'pending', resumed_from_stage: 'parsing' } })
  })
  await page.route('**/api/v1/review-tasks/task-1*', async (route) => {
    expect(route.request().method()).toBe('GET')
    await route.fulfill({ status: 200, json: retried ? { ...task, status: 'pending' } : failedTask })
  })
  await page.route('**/api/v1/contracts/contract-1**', (route) => route.fulfill({
    status: 200,
    json: contract,
  }))

  await page.goto('/reviews/task-1')
  await expect(page.getByRole('heading', { name: '审核失败' })).toBeVisible()
  await page.getByRole('button', { name: '重试失败阶段' }).click()
  await expect(page.getByRole('heading', { name: '等待处理' })).toBeVisible()
  await assertNoHorizontalOverflow(page)
})
