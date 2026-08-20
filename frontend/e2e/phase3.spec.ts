import { expect, test, type Page } from '@playwright/test'

const platformSession = {
  user: {
    id: 'platform-1',
    email: 'platform@example.com',
    display_name: '平台管理员',
    status: 'active',
    is_platform_admin: true,
  },
  memberships: [],
  csrf_token: 'csrf-platform',
}

const organization = {
  id: 'org-1',
  name: '示例企业',
  status: 'active',
  retention_days: 180,
  settings: {
    file_size_limit_bytes: 20971520,
    page_limit: 100,
    concurrent_review_limit: 3,
    warn_on_medium_risk: false,
    ocr_low_confidence_threshold: 0.8,
    retention_days: 180,
    report_watermark: '仅供内部审核',
  },
  version: 1,
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

async function mockPlatformSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: platformSession }))
}

test('platform organization list creates an organization and opens its detail', async ({ page }, testInfo) => {
  await mockPlatformSession(page)
  await page.route('**/api/v1/platform/organizations?*', (route) =>
    route.fulfill({ status: 200, json: { items: [organization], next_cursor: null, has_more: false } }),
  )
  await page.route('**/api/v1/platform/organizations', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: organization })
      return
    }
    await route.fulfill({ status: 200, json: { items: [organization], next_cursor: null, has_more: false } })
  })
  await page.route('**/api/v1/platform/organizations/org-1', (route) =>
    route.fulfill({ status: 200, json: organization }),
  )
  await page.goto('/platform/organizations')

  await expect(page.getByRole('heading', { name: '平台组织' })).toBeVisible()
  await expect(page.getByRole('button', { name: '示例企业' })).toBeVisible()
  await page.getByRole('button', { name: '新建组织' }).click()
  const createDialog = page.getByRole('dialog', { name: '新建组织' })
  await createDialog.getByRole('textbox', { name: /组织名称/ }).fill('新组织')
  await createDialog.getByRole('textbox', { name: /初始管理员邮箱/ }).fill('admin@example.com')
  await createDialog.getByRole('button', { name: '创建组织' }).click()

  await expect(page).toHaveURL(/\/platform\/organizations\/org-1$/)
  await expect(page.getByRole('heading', { name: '组织详情' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '组织名称', exact: true })).toHaveValue('示例企业')
  await page.screenshot({ path: testInfo.outputPath(`organization-detail-${testInfo.project.name}.png`), fullPage: true })
})

test('model configuration keeps secret state visible without a secret input', async ({ page }, testInfo) => {
  await mockPlatformSession(page)
  await page.route('**/api/v1/platform/model-configuration', (route) =>
    route.fulfill({
      status: 200,
      json: {
        provider: 'qwen',
        model: 'qwen-test-model',
        model_source: 'environment',
        timeout_seconds: 60,
        max_retries: 3,
        hard_budget_enabled: false,
        usage_tracking_enabled: true,
        organization_overrides_allowed: false,
        secret_configured: false,
        status: 'active',
        version: 1,
      },
    }),
  )
  await page.goto('/platform/model-configuration')

  await expect(page.getByRole('heading', { name: '模型配置', exact: true })).toBeVisible()
  await expect(page.getByText('模型环境未配置完成')).toBeVisible()
  await expect(page.getByText('qwen-test-model')).toBeVisible()
  await expect(page.getByLabel(/密钥|API Key/i)).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath(`model-configuration-${testInfo.project.name}.png`), fullPage: true })
})

test('organization settings submits only changed non-secret values', async ({ page }, testInfo) => {
  const organizationSession = {
    ...platformSession,
    user: { ...platformSession.user, is_platform_admin: false, display_name: '组织管理员' },
    memberships: [
      {
        organization_id: 'org-1',
        organization_name: '示例企业',
        role: 'org_admin',
        status: 'active',
      },
    ],
  }
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: organizationSession }))
  await page.route('**/api/v1/organizations/org-1', (route) =>
    route.fulfill({
      status: 200,
      json: {
        id: 'org-1',
        name: '示例企业',
        status: 'active',
        my_role: 'org_admin',
        permissions: ['organization:read'],
      },
    }),
  )
  await page.route('**/api/v1/organizations/org-1/settings', async (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>
      expect(body).toEqual({ warn_on_medium_risk: true, version: 1 })
      await route.fulfill({ status: 200, json: { ...organization.settings, warn_on_medium_risk: true, version: 2 } })
      return
    }
    await route.fulfill({ status: 200, json: { ...organization.settings, version: 1 } })
  })
  await page.goto('/organizations/org-1/settings')

  await expect(page.getByRole('heading', { name: '组织设置' })).toBeVisible()
  await page.locator('.el-switch').filter({ has: page.getByLabel('中风险生成预警') }).click()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByRole('heading', { name: '组织设置', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`organization-settings-${testInfo.project.name}.png`), fullPage: true })
})
