import { expect, test, type Page } from '@playwright/test'

const adminSession = {
  user: {
    id: 'admin-1',
    email: 'admin@example.com',
    display_name: '组织管理员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'org_admin',
    status: 'active',
  }],
  csrf_token: 'csrf-clause-templates',
}

const reviewerSession = {
  ...adminSession,
  user: { ...adminSession.user, id: 'reviewer-1', display_name: '审核员' },
  memberships: [{ ...adminSession.memberships[0], role: 'reviewer' }],
}

const clause = {
  id: 'clause-1',
  clause_key: 'payment',
  name: '付款',
  standard_text: '验收后 30 日内付款。',
  allowed_deviation: '期限可协商但必须明确。',
  severity: 'medium',
  applicability: {},
  suggestion: '请补充付款期限。',
  enabled: true,
  order_no: 1,
}

const template = {
  organization_id: 'org-1',
  id: 'template-1',
  name: '采购合同基线',
  contract_type: 'purchase',
  business_scenario: 'standard',
  status: 'active',
  current_published_version_id: 'version-1',
  is_default: true,
  version: 1,
}

const publishedVersion = {
  organization_id: 'org-1',
  id: 'version-1',
  template_id: 'template-1',
  version_no: 1,
  status: 'published',
  change_note: '初始化条款',
  effective_at: '2026-08-19T06:00:00Z',
  published_by: 'admin-1',
  version: 1,
  is_default: true,
  current_published_version_id: 'version-1',
  clauses: [clause],
}

const draftVersion = {
  ...publishedVersion,
  id: 'version-2',
  version_no: 2,
  status: 'draft',
  change_note: '准备发布',
  effective_at: null,
  published_by: null,
  version: 1,
}

async function mockSession(page: Page, session: typeof adminSession): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) => route.fulfill({ status: 200, json: session }))
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
}

test('admin can inspect a template, open a draft editor, and publish a version', async ({ page }) => {
  await mockSession(page, adminSession)
  await page.route('**/api/v1/clause-templates?*', (route) => route.fulfill({
    status: 200,
    json: { items: [template], next_cursor: null, has_more: false },
  }))
  await page.route('**/api/v1/clause-templates/template-1?*', (route) => route.fulfill({
    status: 200,
    json: { ...template, versions: [{ ...publishedVersion, clauses: [clause] }] },
  }))
  await page.route('**/api/v1/clause-templates/template-1/versions', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postDataJSON()).toMatchObject({
      change_note: '准备发布',
      source_version_id: 'version-1',
      clauses: [{ clause_key: 'payment' }],
    })
    await route.fulfill({ status: 201, json: draftVersion })
  })
  await page.route('**/api/v1/clause-template-versions/version-2', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, json: draftVersion })
      return
    }
    expect(route.request().method()).toBe('PATCH')
    await route.fulfill({ status: 200, json: { ...draftVersion, version: 2 } })
  })
  await page.route('**/api/v1/clause-template-versions/version-2/publish', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().postDataJSON()).toEqual({})
    await route.fulfill({ status: 200, json: { ...draftVersion, status: 'published', effective_at: '2026-08-20T06:00:00Z', published_by: 'admin-1', version: 3 } })
  })

  await page.goto('/clause-templates')
  await expect(page.getByRole('heading', { name: '条款模板', exact: true })).toBeVisible()
  await expect(page.getByText('采购合同基线')).toBeVisible()
  await page.getByRole('button', { name: '查看详情' }).click()
  await expect(page).toHaveURL(/\/clause-templates\/template-1$/)
  await expect(page.getByRole('heading', { name: '采购合同基线', exact: true })).toBeVisible()
  await expect(page.getByText('版本历史（1）')).toBeVisible()
  await page.getByRole('button', { name: '新建草稿版本' }).click()
  await page.getByLabel('变更说明').fill('准备发布')
  await page.getByRole('button', { name: '创建草稿' }).click()

  await expect(page).toHaveURL(/\/clause-templates\/template-1\/versions\/version-2$/)
  await expect(page.getByRole('heading', { name: '编辑条款草稿 v2' })).toBeVisible()
  await page.getByRole('button', { name: '发布版本' }).click()
  await page.getByRole('button', { name: '发布', exact: true }).click()
  await expect(page.getByRole('heading', { name: '查看已发布条款 v2' })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存草稿' })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
})

test('reviewer can read published templates but has no write controls', async ({ page }) => {
  await mockSession(page, reviewerSession)
  await page.route('**/api/v1/clause-templates?*', (route) => route.fulfill({
    status: 200,
    json: { items: [template], next_cursor: null, has_more: false },
  }))
  await page.route('**/api/v1/clause-templates/template-1?*', (route) => route.fulfill({
    status: 200,
    json: { ...template, versions: [{ ...publishedVersion, clauses: [clause] }] },
  }))

  await page.goto('/clause-templates')
  await expect(page.getByText('采购合同基线')).toBeVisible()
  await expect(page.getByRole('button', { name: '新建模板' })).toHaveCount(0)
  await page.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('heading', { name: '采购合同基线', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新建草稿版本' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '停用模板' })).toHaveCount(0)
  await assertNoHorizontalOverflow(page)
})
