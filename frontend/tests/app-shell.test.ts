import { cleanup, render, screen } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test } from 'vitest'

import AppShell from '@/components/AppShell.vue'
import type { AuthSession } from '@/api/types'
import { currentOrganizationId, selectCurrentOrganization, sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionState.current = null
  sessionState.loaded = false
})

test('platform admins with multiple organizations see the organization selector', async () => {
  const session: AuthSession = {
    user: {
      id: 'platform-admin',
      email: 'platform@example.com',
      display_name: '平台管理员',
      status: 'active',
      is_platform_admin: true,
    },
    memberships: [
      {
        organization_id: 'org-1',
        organization_name: '第一组织',
        role: 'org_admin',
        status: 'active',
      },
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'reviewer',
        status: 'active',
      },
    ],
    csrf_token: 'csrf-platform',
  }
  sessionState.current = session
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-1')).toBe(true)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  render(AppShell, { global: { plugins: [router, ElementPlus] } })

  expect(screen.getByRole('combobox', { name: '当前组织' })).toBeInTheDocument()
  expect(screen.getAllByText('平台管理员').length).toBeGreaterThan(0)
  expect(currentOrganizationId.value).toBe('org-1')
})
