import { expect, test, type Page } from '@playwright/test'

const adminSession = {
  user: {
    id: 'admin-1',
    email: 'admin@example.com',
    display_name: '管理员',
    status: 'active',
    is_platform_admin: true,
  },
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'org_admin',
    status: 'active',
  }],
  csrf_token: 'csrf-phase14a',
}

async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: adminSession }))
  await page.route('**/api/v1/notifications/unread-count', (route) => route.fulfill({ status: 200, json: { unread_count: 0 } }))
}

async function mockAudit(page: Page): Promise<void> {
  await page.route('**/api/v1/audit-logs*', (route) => route.fulfill({
    status: 200,
    json: {
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
    },
  }))
  await page.route('**/api/v1/platform/audit-logs*', (route) => route.fulfill({
    status: 200,
    json: {
      items: [{
        id: 'audit-platform-1',
        organization_id: null,
        action: 'platform.model_configuration_updated',
        resource_type: 'platform_model_configuration',
        resource_id: null,
        actor_id: 'admin-1',
        request_id: 'req-platform-1',
        before_summary: null,
        after_summary: { status: 'active' },
        created_at: '2026-08-21T00:00:00Z',
      }],
      next_cursor: null,
      has_more: false,
    },
  }))
}

async function mockMetrics(page: Page): Promise<void> {
  await page.route('**/api/v1/organizations/org-1/metrics/reviews*', (route) => route.fulfill({
    status: 200,
    json: {
      from: '2026-08-01T00:00:00Z', to: '2026-08-21T00:00:00Z', review_count: 12,
      completed_count: 9, failed_count: 1, average_duration_ms: 4200,
      parse_failure_rate: 0.1, model_failure_rate: 0.2, manual_edit_rate: 0.3,
    },
  }))
  await page.route('**/api/v1/organizations/org-1/metrics/warnings*', (route) => route.fulfill({
    status: 200,
    json: {
      from: '2026-08-01T00:00:00Z', to: '2026-08-21T00:00:00Z', created_count: 8,
      unprocessed_count: 2, closed_count: 5, closure_rate: 0.625,
      false_positive_rate: 0.125, average_unprocessed_duration_ms: 86_400_000,
      by_risk_type: [{ risk_type: 'unlimited_liability', count: 4 }],
    },
  }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('Phase 14A admin pages render safe audit and operations surfaces', async ({ page }) => {
  await mockSession(page)
  await mockAudit(page)
  await mockMetrics(page)

  await page.goto('/audit-logs')
  await expect(page.getByRole('heading', { name: '组织审计' })).toBeVisible()
  await expect(page.getByText('review_task.completed')).toBeVisible()
  await page.getByRole('button', { name: '查看安全摘要' }).click()
  await expect(page.getByText('安全摘要')).toBeVisible()
  await assertNoHorizontalOverflow(page)

  await page.goto('/organizations/org-1/metrics')
  await expect(page.getByRole('heading', { name: '运营指标' })).toBeVisible()
  await expect(page.getByText('unlimited_liability')).toBeVisible()
  await expect(page.getByText('30.0%')).toBeVisible()
  await assertNoHorizontalOverflow(page)
})

test('Phase 14A platform audit stays in the platform-admin navigation', async ({ page }) => {
  await mockSession(page)
  await mockAudit(page)

  await page.goto('/platform/audit-logs')
  await expect(page.getByRole('heading', { name: '平台审计' })).toBeVisible()
  await expect(page.getByText('platform.model_configuration_updated')).toBeVisible()
  await expect(page.getByText('合同目录')).toHaveCount(1)
  await assertNoHorizontalOverflow(page)
})
