import { expect, test } from '@playwright/test'

const session = {
  user: {
    id: 'user-1',
    email: 'legal@example.com',
    display_name: '李法务',
    status: 'active',
    is_platform_admin: false,
  },
  organizations: [{ id: 'org-1', name: '示例企业', role: 'reviewer' }],
  csrf_token: 'csrf_test',
}

test('login enables only after required fields and establishes a session', async ({ page }, testInfo) => {
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ status: 200, json: session }))
  await page.goto('/login')

  const submit = page.getByRole('button', { name: '登录' })
  await expect(submit).toBeDisabled()
  await page.getByLabel('邮箱').fill('legal@example.com')
  await page.getByLabel('密码').fill('correct-horse-battery')
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('会话已建立')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`login-${testInfo.project.name}.png`), fullPage: true })
})

test('password reset shows generic accepted state', async ({ page }, testInfo) => {
  await page.route('**/api/v1/auth/password-reset/request', (route) =>
    route.fulfill({
      status: 202,
      json: { accepted: true, message: '如果账号存在，系统将继续处理密码重置请求。' },
    }),
  )
  await page.goto('/password-reset')
  await page.getByLabel('邮箱').fill('legal@example.com')
  await page.getByRole('button', { name: '发送请求' }).click()
  await expect(page.getByText('如果账号存在，系统将继续处理密码重置请求。')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`password-reset-${testInfo.project.name}.png`), fullPage: true })
})

test('reset page explains a missing token', async ({ page }) => {
  await page.goto('/password-reset/confirm')
  await expect(page.getByText('重置链接无效')).toBeVisible()
  await expect(page.getByRole('button', { name: '保存新密码' })).toHaveCount(0)
})

test('expired reset token keeps a re-request path', async ({ page }, testInfo) => {
  await page.route('**/api/v1/auth/password-reset/confirm', (route) =>
    route.fulfill({
      status: 400,
      json: {
        error: {
          code: 'TOKEN_EXPIRED',
          message: '令牌已过期。',
          request_id: 'req_test',
        },
      },
    }),
  )
  await page.goto('/password-reset/confirm?token=reset_test')
  await page.getByRole('textbox', { name: '新密码', exact: true }).fill('new-correct-password')
  await page.getByRole('textbox', { name: '确认新密码', exact: true }).fill('new-correct-password')
  await page.getByRole('button', { name: '保存新密码' }).click()
  await expect(page.getByText('重新申请重置链接')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`reset-expired-${testInfo.project.name}.png`), fullPage: true })
})

test('invitation acceptance shows a success result', async ({ page }, testInfo) => {
  await page.route('**/api/v1/auth/invitations/accept', (route) =>
    route.fulfill({
      status: 200,
      json: { user_id: 'user-1', organization_id: 'org-1', role: 'reviewer', status: 'active' },
    }),
  )
  await page.goto('/invitations/accept?token=invite_test')
  await page.getByRole('button', { name: '接受邀请' }).click()
  await expect(page.getByText('邀请已接受')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`invitation-${testInfo.project.name}.png`), fullPage: true })
})

test('invitation page explains a missing token', async ({ page }) => {
  await page.goto('/invitations/accept')
  await expect(page.getByText('邀请链接无效')).toBeVisible()
  await expect(page.getByRole('button', { name: '接受邀请' })).toHaveCount(0)
})
