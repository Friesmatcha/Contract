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
  csrf_token: 'csrf-phase11',
}

const warning = {
  id: 'warning-1',
  contract_id: 'contract-1',
  review_task_id: 'task-1',
  severity: 'high',
  status: 'pending_confirmation',
  priority: 'high',
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
    kind: 'pdf_page',
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
    to_status: 'pending_confirmation',
    actor_id: null,
    note: null,
    assignee_id: null,
    due_at: null,
    created_at: '2026-08-20T03:34:00Z',
  }],
}

async function mockWarningCenter(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: session }))
  await page.route('**/api/v1/notifications/unread-count', (route) => route.fulfill({ status: 200, json: { unread_count: 1 } }))
  await page.route('**/api/v1/warnings?*', (route) => route.fulfill({
    status: 200,
    json: { items: [warning], next_cursor: null, has_more: false, summary: { unprocessed_count: 1, high_count: 1 } },
  }))
  await page.route('**/api/v1/warnings/warning-1', (route) => route.fulfill({ status: 200, json: detail }))
  await page.route('**/api/v1/notifications?*', (route) => route.fulfill({
    status: 200,
    json: {
      items: [{
        id: 'notification-1',
        warning_id: 'warning-1',
        channel: 'in_app',
        status: 'unread',
        title: '发现高风险预警',
        body: '请前往预警中心复核。',
        created_at: '2026-08-20T03:34:05Z',
      }],
      next_cursor: null,
      has_more: false,
    },
  }))
  await page.route('**/api/v1/notifications/notification-1/read', (route) => route.fulfill({
    status: 200,
    json: { id: 'notification-1', status: 'read', read_at: '2026-08-20T03:35:00Z' },
  }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('WARNING-001 and WARNING-002 are usable at desktop widths', async ({ page }) => {
  await mockWarningCenter(page)
  await page.goto('/warnings')

  await expect(page.getByRole('heading', { name: '预警中心' })).toBeVisible()
  await expect(page.getByRole('button', { name: /查看/ })).toBeVisible()
  await expect(page.getByText('责任条款未设置上限')).toHaveCount(0)
  await page.getByRole('button', { name: /查看/ }).click()

  await expect(page.getByRole('heading', { name: '预警详情' })).toBeVisible()
  await expect(page.getByText('责任条款未设置上限')).toBeVisible()
  await assertNoHorizontalOverflow(page)
})

test('NOTIFY-001 opens from the header and navigates to a warning', async ({ page }) => {
  await mockWarningCenter(page)
  await page.goto('/warnings')

  await page.getByRole('button', { name: '通知中心' }).click()
  await expect(page.getByText('发现高风险预警')).toBeVisible()
  await page.getByRole('button', { name: /发现高风险预警/ }).click()

  await expect(page).toHaveURL(/\/warnings\/warning-1$/)
  await expect(page.getByRole('heading', { name: '预警详情' })).toBeVisible()
  await assertNoHorizontalOverflow(page)
})
