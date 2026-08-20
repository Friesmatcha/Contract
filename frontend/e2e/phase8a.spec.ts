import { expect, test, type Page } from '@playwright/test'

const adminSession = {
  user: {
    id: 'admin-1',
    email: 'admin@example.com',
    display_name: '组织管理员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [
    {
      organization_id: 'org-1',
      organization_name: '示例企业',
      role: 'org_admin',
      status: 'active',
    },
  ],
  csrf_token: 'csrf-risk-rules',
}

const reviewerSession = {
  ...adminSession,
  user: { ...adminSession.user, id: 'reviewer-1', display_name: '审核员' },
  memberships: [{ ...adminSession.memberships[0], role: 'reviewer' }],
}

const viewerSession = {
  ...adminSession,
  user: { ...adminSession.user, id: 'viewer-1', display_name: '查看者' },
  memberships: [{ ...adminSession.memberships[0], role: 'viewer' }],
}

const publishedRule = {
  id: 'rule-1',
  rule_key: 'payment_cap',
  risk_type: 'payment_terms',
  engine: 'deterministic',
  condition: {
    operator: 'amount_threshold',
    field: 'contract_amount',
    comparison: 'gt',
    value: '30',
  },
  severity: 'high',
  suggestion: '请复核付款条件。',
  enabled: true,
}

const publishedVersion = {
  id: 'version-1',
  organization_id: 'org-1',
  version_no: 1,
  status: 'published',
  change_note: '初始化规则',
  effective_at: '2026-08-19T06:00:00Z',
  published_by: 'admin-1',
  rule_count: 1,
  rules: [publishedRule],
}

const draftVersion = {
  id: 'version-2',
  organization_id: 'org-1',
  bundle_id: 'bundle-1',
  version_no: 2,
  status: 'draft',
  change_note: '待发布规则',
  effective_at: null,
  published_by: null,
  version: 1,
  is_default: true,
  current_published_version_id: 'version-1',
  rules: [publishedRule],
}

const publishedDraftVersion = {
  ...draftVersion,
  status: 'published',
  effective_at: '2026-08-19T07:00:00Z',
  published_by: 'admin-1',
  version: 3,
  current_published_version_id: 'version-2',
}

const bundle = {
  id: 'bundle-1',
  organization_id: 'org-1',
  name: '采购风险基线',
  status: 'active',
  current_published_version_id: 'version-1',
  is_default: true,
  version: 1,
}

const bundleDetail = {
  ...bundle,
  versions: [publishedVersion],
}

async function mockSession(page: Page, session: typeof adminSession): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 200, json: session }),
  )
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBeTruthy()
}

test('admin can inspect a bundle, create a draft, save it, and publish it', async ({ page }, testInfo) => {
  await mockSession(page, adminSession)
  await page.route('**/api/v1/risk-rule-bundles?*', (route) =>
    route.fulfill({ status: 200, json: { items: [bundle], next_cursor: null, has_more: false } }),
  )
  await page.route('**/api/v1/risk-rule-bundles/bundle-1?*', (route) =>
    route.fulfill({ status: 200, json: bundleDetail }),
  )
  await page.route('**/api/v1/risk-rule-bundles/bundle-1/versions', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postDataJSON()).toMatchObject({
      change_note: '准备发布',
      source_version_id: 'version-1',
      rules: [{ rule_key: 'payment_cap' }],
    })
    await route.fulfill({ status: 201, json: { ...draftVersion, change_note: '准备发布' } })
  })
  await page.route('**/api/v1/risk-rule-bundle-versions/version-2', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, json: { ...draftVersion, change_note: '准备发布' } })
      return
    }
    expect(route.request().method()).toBe('PATCH')
    expect(route.request().postDataJSON()).toMatchObject({
      change_note: '准备发布',
      version: 1,
      rules: [{ rule_key: 'payment_cap' }],
    })
    await route.fulfill({ status: 200, json: { ...draftVersion, change_note: '准备发布', version: 2 } })
  })
  await page.route('**/api/v1/risk-rule-bundle-versions/version-2/publish', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postDataJSON()).toEqual({})
    await route.fulfill({ status: 200, json: publishedDraftVersion })
  })

  await page.goto('/risk-rule-bundles')
  await expect(page.getByRole('heading', { name: '风险规则', exact: true })).toBeVisible()
  await expect(page.getByText('采购风险基线')).toBeVisible()
  await expect(page.getByText('默认', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看详情' }).click()

  await expect(page).toHaveURL(/\/risk-rule-bundles\/bundle-1$/)
  await expect(page.getByRole('heading', { name: '采购风险基线', exact: true })).toBeVisible()
  await expect(page.getByText('当前版本规则预览')).toBeVisible()
  await page.getByRole('button', { name: '新建草稿' }).click()
  await page.getByLabel('变更说明').fill('准备发布')
  await page.getByRole('button', { name: '创建草稿' }).click()

  await expect(page).toHaveURL(/\/risk-rule-bundle-versions\/version-2$/)
  await expect(page.getByRole('heading', { name: '编辑规则草稿 v2' })).toBeVisible()
  await page.getByRole('button', { name: '发布版本' }).click()
  await page.getByRole('button', { name: '发布', exact: true }).click()
  await expect(page.getByRole('heading', { name: '查看已发布规则 v2' })).toBeVisible()
  await expect(page.locator('.el-message-box')).toHaveCount(0)
  await expect(page.getByText('已发布', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存草稿' })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
  await page.screenshot({
    path: testInfo.outputPath(`risk-rule-published-${testInfo.project.name}.png`),
    fullPage: true,
  })
})

test('reviewer can read published rules but has no write controls', async ({ page }, testInfo) => {
  await mockSession(page, reviewerSession)
  await page.route('**/api/v1/risk-rule-bundles?*', (route) =>
    route.fulfill({ status: 200, json: { items: [bundle], next_cursor: null, has_more: false } }),
  )
  await page.route('**/api/v1/risk-rule-bundles/bundle-1?*', (route) =>
    route.fulfill({ status: 200, json: bundleDetail }),
  )

  await page.goto('/risk-rule-bundles')
  await expect(page.getByText('采购风险基线')).toBeVisible()
  await expect(page.getByRole('button', { name: '新建规则集' })).toHaveCount(0)
  await page.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('heading', { name: '采购风险基线', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '编辑规则集' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新建草稿' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '停用规则集' })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
  await page.screenshot({
    path: testInfo.outputPath(`risk-rule-reviewer-${testInfo.project.name}.png`),
    fullPage: true,
  })
})

test('viewer has no risk-rule navigation and receives a forbidden state', async ({ page }, testInfo) => {
  await mockSession(page, viewerSession)
  await page.route('**/api/v1/risk-rule-bundles?*', (route) =>
    route.fulfill({
      status: 403,
      json: {
        error: {
          code: 'FORBIDDEN',
          message: '当前账户没有风险规则访问权限。',
          request_id: 'req-viewer-risk',
        },
      },
    }),
  )

  await page.goto('/risk-rule-bundles')
  await expect(page.getByText('无法访问风险规则')).toBeVisible()
  await expect(page.getByText('当前账户没有风险规则访问权限。')).toBeVisible()
  await expect(page.getByRole('menuitem', { name: '风险规则' })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
  await page.screenshot({
    path: testInfo.outputPath(`risk-rule-viewer-forbidden-${testInfo.project.name}.png`),
    fullPage: true,
  })
})

test('rule condition editor stays single-column inside the narrow drawer', async ({ page }) => {
  await mockSession(page, adminSession)
  await page.route('**/api/v1/risk-rule-bundle-versions/version-2', (route) =>
    route.fulfill({ status: 200, json: { ...draftVersion, current_published_version_id: 'version-1' } }),
  )

  await page.goto('/risk-rule-bundle-versions/version-2')
  await expect(page.getByRole('heading', { name: '编辑规则草稿 v2' })).toBeVisible()
  await page.getByRole('button', { name: '新增规则' }).click()

  const drawer = page.locator('.el-drawer').filter({ hasText: '新增规则' })
  await expect(drawer).toBeVisible()
  const conditionGrid = drawer.locator('.condition-editor-grid').first()
  await expect(conditionGrid).toBeVisible()
  expect(
    await conditionGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length),
  ).toBe(1)
  expect(
    await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy()
})
