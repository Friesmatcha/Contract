import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, test, vi } from 'vitest'

import InvitationAcceptPage from '@/pages/auth/InvitationAcceptPage.vue'
import LoginPage from '@/pages/auth/LoginPage.vue'
import PasswordResetConfirmPage from '@/pages/auth/PasswordResetConfirmPage.vue'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function renderPage(component: object, path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginPage },
      { path: '/password-reset/confirm', component: PasswordResetConfirmPage },
      { path: '/invitations/accept', component: InvitationAcceptPage },
    ],
  })
  await router.push(path)
  await router.isReady()
  return { router, ...render(component, { global: { plugins: [router, ElementPlus] } }) }
}

function inputAt(index: number): HTMLInputElement {
  const input = document.querySelectorAll('input').item(index)
  if (!(input instanceof HTMLInputElement)) throw new Error(`Missing input at index ${index}`)
  return input
}

describe('authentication pages', () => {
  test('login submit is disabled until both fields are filled', async () => {
    await renderPage(LoginPage, '/login')

    const button = screen.getByRole('button', { name: '登录' })
    expect(button).toBeDisabled()
    await fireEvent.update(inputAt(0), 'legal@example.com')
    await fireEvent.update(inputAt(1), 'correct-horse-battery')
    expect(button).not.toBeDisabled()
  })

  test('password reset confirmation stays on success result', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await renderPage(PasswordResetConfirmPage, '/password-reset/confirm?token=reset_test')

    await fireEvent.update(inputAt(0), 'new-correct-password')
    await fireEvent.update(inputAt(1), 'new-correct-password')
    await fireEvent.click(screen.getByRole('button', { name: '保存新密码' }))

    await waitFor(() => expect(screen.getByText('密码已更新')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '返回登录' })).toBeInTheDocument()
  })

  test('expired reset token offers a new request link', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'TOKEN_EXPIRED',
            message: '令牌已过期。',
            request_id: 'req_test',
          },
        }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await renderPage(PasswordResetConfirmPage, '/password-reset/confirm?token=reset_test')

    await fireEvent.update(inputAt(0), 'new-correct-password')
    await fireEvent.update(inputAt(1), 'new-correct-password')
    await fireEvent.click(screen.getByRole('button', { name: '保存新密码' }))

    await waitFor(() => expect(screen.getByText('重新申请重置链接')).toBeInTheDocument())
  })

  test('invitation acceptance stays on success result', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: 'user-1',
          organization_id: 'org-1',
          role: 'reviewer',
          status: 'active',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await renderPage(InvitationAcceptPage, '/invitations/accept?token=invite_test')

    await fireEvent.click(screen.getByRole('button', { name: '接受邀请' }))

    await waitFor(() => expect(screen.getByText('邀请已接受')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '返回登录' })).toBeInTheDocument()
  })
})
