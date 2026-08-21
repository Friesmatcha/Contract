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
  csrf_token: 'csrf-phase13',
}

const baseReport = {
  id: 'report-1',
  display_no: 'RPT-20260821-000001',
  review_task_id: 'task-1',
  format: 'html',
  template_version: 'report-v1',
  created_at: '2026-08-21T00:00:00Z',
  generated_at: '2026-08-21T00:01:00Z',
  expires_at: '2027-02-17T00:01:00Z',
  download_available: true,
  error_code: null,
}

async function mockSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: session }))
  await page.route('**/api/v1/notifications/unread-count', (route) => route.fulfill({
    status: 200,
    json: { unread_count: 0 },
  }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

async function mockDownload(page: Page): Promise<void> {
  await page.route('**/api/v1/reports/report-1/download*', (route) => route.fulfill({
    status: 200,
    contentType: 'text/html',
    body: '<!doctype html><html><body>报告</body></html>',
  }))
}

test('REPORT-001 shows loading then polls generating into ready preview', async ({ page }) => {
  await mockSession(page)
  await mockDownload(page)
  let reads = 0
  await page.route('**/api/v1/reports/report-1', async (route) => {
    const firstRead = reads++ === 0
    if (firstRead) await new Promise((resolve) => setTimeout(resolve, 300))
    await route.fulfill({
      status: 200,
      json: firstRead
        ? { ...baseReport, status: 'generating', generated_at: null, expires_at: null, download_available: false }
        : { ...baseReport, status: 'ready' },
    })
  })

  await page.goto('/reports/report-1')
  await expect(page.locator('.el-skeleton').first()).toBeVisible()
  await expect(page.getByText('正在生成', { exact: true })).toBeVisible()
  await expect(page.getByText('已就绪')).toBeVisible({ timeout: 10000 })
  await expect(page.locator('iframe[title="报告 HTML 预览"]')).toBeVisible()
  await assertNoHorizontalOverflow(page)
})

test('REPORT-001 shows failed state and returns to results for regeneration', async ({ page }) => {
  await mockSession(page)
  await page.route('**/api/v1/reports/report-1', (route) => route.fulfill({
    status: 200,
    json: { ...baseReport, status: 'failed', download_available: false, error_code: 'REPORT_RENDER_FAILED' },
  }))

  await page.goto('/reports/report-1')
  await expect(page.getByText('生成失败', { exact: true })).toBeVisible()
  await expect(page.getByText('REPORT_RENDER_FAILED')).toBeVisible()
  await page.getByRole('button', { name: '重新生成' }).click()
  await expect(page).toHaveURL(/\/reviews\/task-1\/results$/)
  await assertNoHorizontalOverflow(page)
})

test('REPORT-001 shows expired state without a download action', async ({ page }) => {
  await mockSession(page)
  await page.route('**/api/v1/reports/report-1', (route) => route.fulfill({
    status: 200,
    json: { ...baseReport, status: 'expired', download_available: false },
  }))

  await page.goto('/reports/report-1')
  await expect(page.getByText('报告已过期')).toBeVisible()
  await expect(page.getByRole('link', { name: /下载/ })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
})

test('REPORT-001 hides a forbidden report behind a safe error state', async ({ page }) => {
  await mockSession(page)
  await page.route('**/api/v1/reports/report-1', (route) => route.fulfill({
    status: 404,
    json: { error: { code: 'REPORT_NOT_FOUND', message: '报告不存在。', request_id: 'req-report-404' } },
  }))

  await page.goto('/reports/report-1')
  await expect(page.getByText('无法访问报告')).toBeVisible()
  await expect(page.getByText('请求 ID：req-report-404')).toBeVisible()
  await expect(page.getByText('合同风险分析报告')).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
})
