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
  csrf_token: 'csrf-org-admin',
}

const member = {
  id: 'member-1',
  user_id: null,
  email: 'reviewer@example.com',
  display_name: null,
  role: 'reviewer',
  status: 'pending_invitation',
  invited_at: '2026-08-19T04:00:00Z',
  email_delivery_status: 'sent',
  version: 1,
  created_at: '2026-08-19T04:00:00Z',
  updated_at: '2026-08-19T04:00:00Z',
}

async function mockOrganizationSession(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 200, json: organizationSession }),
  )
}

test('member management sends an invitation and keeps delivery status visible', async ({ page }, testInfo) => {
  await mockOrganizationSession(page)
  await page.route('**/api/v1/organizations/org-1/members*', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: { ...member, email: 'new-user@example.com' } })
      return
    }
    await route.fulfill({ status: 200, json: { items: [member], next_cursor: null, has_more: false } })
  })
  await page.goto('/organizations/org-1/members')

  await expect(page.getByRole('heading', { name: '成员管理' })).toBeVisible()
  await expect(page.getByText('reviewer@example.com')).toBeVisible()
  await expect(page.getByText('已发送')).toBeVisible()
  await page.getByRole('button', { name: '邀请成员' }).click()
  await page.getByRole('textbox', { name: '成员邮箱' }).fill('new-user@example.com')
  await page.getByRole('button', { name: '发送邀请' }).click()

  await expect(page.getByRole('heading', { name: '成员管理' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`members-${testInfo.project.name}.png`), fullPage: true })
})

test('support access management shows the read-only security boundary and empty state', async ({ page }, testInfo) => {
  await mockOrganizationSession(page)
  await page.route('**/api/v1/organizations/org-1/support-access-grants*', (route) =>
    route.fulfill({ status: 200, json: { items: [], next_cursor: null, has_more: false } }),
  )
  await page.goto('/organizations/org-1/support-access-grants')

  await expect(page.getByRole('heading', { name: '支持授权' })).toBeVisible()
  await expect(page.getByText('只读支持访问，最长 4 小时，每次访问都会产生审计记录。')).toBeVisible()
  await expect(page.getByText('暂无支持授权记录')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`support-access-${testInfo.project.name}.png`), fullPage: true })
})
