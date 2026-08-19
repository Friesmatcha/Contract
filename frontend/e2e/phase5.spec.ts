import { expect, test, type Page } from '@playwright/test'

const organizationSession = {
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
  csrf_token: 'csrf-contract',
}

const activeContract = {
  id: 'contract-1',
  display_no: 'CTR-20260819-000001',
  title: '供应商采购合同',
  declared_type: 'purchase',
  status: 'active',
  owner_id: 'admin-1',
  current_file: null,
  files: [],
  latest_review: null,
  created_at: '2026-08-19T06:00:00Z',
  updated_at: '2026-08-19T06:00:00Z',
  version: 1,
}

const viewer = {
  id: 'member-viewer',
  user_id: 'viewer-1',
  email: 'viewer@example.com',
  display_name: '业务查看者',
  role: 'viewer',
  status: 'active',
  invited_at: null,
  email_delivery_status: null,
  version: 1,
  created_at: '2026-08-19T06:00:00Z',
  updated_at: '2026-08-19T06:00:00Z',
}

async function mockOrganizationSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 200, json: organizationSession }),
  )
}

test('contract list filters by owner and opens the detail view', async ({ page }, testInfo) => {
  await mockOrganizationSession(page)
  await page.route('**/api/v1/contracts?*', (route) =>
    route.fulfill({
      status: 200,
      json: { items: [activeContract], next_cursor: null, has_more: false },
    }),
  )
  await page.route('**/api/v1/contracts/contract-1', (route) =>
    route.fulfill({ status: 200, json: activeContract }),
  )
  await page.goto('/contracts')

  await expect(page.getByRole('heading', { name: '合同目录' })).toBeVisible()
  await expect(page.getByText('供应商采购合同')).toBeVisible()
  await page.getByLabel('负责人 ID').fill('admin-1')
  await page.getByRole('button', { name: '应用筛选' }).click()
  await expect(page.getByText('供应商采购合同')).toBeVisible()
  await page.getByRole('button', { name: '供应商采购合同' }).click()
  await expect(page).toHaveURL(/\/contracts\/contract-1$/)
  await expect(page.getByRole('heading', { name: '供应商采购合同' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`contract-list-detail-${testInfo.project.name}.png`), fullPage: true })
})

test('contract detail supports metadata, archive/restore, and viewer access actions', async ({ page }, testInfo) => {
  let contract = { ...activeContract }
  await mockOrganizationSession(page)
  await page.route('**/api/v1/contracts/contract-1', async (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as { title: string; version: number }
      contract = { ...contract, title: body.title, version: body.version + 1 }
      await route.fulfill({ status: 200, json: contract })
      return
    }
    await route.fulfill({ status: 200, json: contract })
  })
  await page.route('**/api/v1/contracts/contract-1/archive', async (route) => {
    contract = { ...contract, status: 'archived', version: contract.version + 1 }
    await route.fulfill({
      status: 200,
      json: { id: contract.id, status: contract.status, archived_at: '2026-08-19T07:00:00Z' },
    })
  })
  await page.route('**/api/v1/contracts/contract-1/restore', async (route) => {
    contract = { ...contract, status: 'active', version: contract.version + 1 }
    await route.fulfill({ status: 200, json: { id: contract.id, status: contract.status, archived_at: null } })
  })
  await page.route('**/api/v1/contracts/contract-1/access-grants/viewer-1', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({ status: 200, json: { contract_id: contract.id, user_id: 'viewer-1', access_level: 'read' } })
      return
    }
    await route.fulfill({ status: 204 })
  })
  await page.route('**/api/v1/organizations/org-1/members*', (route) =>
    route.fulfill({ status: 200, json: { items: [viewer], next_cursor: null, has_more: false } }),
  )
  await page.goto('/contracts/contract-1')

  await expect(page.getByRole('heading', { name: '供应商采购合同' })).toBeVisible()
  await page.getByRole('button', { name: '编辑元数据' }).click()
  await page.getByLabel('编辑合同名称').fill('供应商采购合同（修订）')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByRole('heading', { name: '供应商采购合同（修订）' })).toBeVisible()

  await page.getByRole('combobox', { name: '选择 viewer' }).click()
  await page.getByRole('option', { name: '业务查看者' }).click()
  await page.getByRole('button', { name: '授予查看权限' }).click()
  await expect(page.getByRole('combobox', { name: '选择 viewer' })).toBeVisible()

  await page.getByRole('button', { name: '归档', exact: true }).click()
  await page.locator('.el-message-box__btns').getByRole('button', { name: '归档', exact: true }).click()
  await expect(page.getByText('已归档')).toBeVisible()
  await expect(page.getByRole('button', { name: '编辑元数据' })).toHaveCount(0)

  await page.getByRole('button', { name: '恢复', exact: true }).click()
  await page.locator('.el-message-box__btns').getByRole('button', { name: '恢复', exact: true }).click()
  await expect(page.getByText('活跃')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`contract-detail-${testInfo.project.name}.png`), fullPage: true })
})
