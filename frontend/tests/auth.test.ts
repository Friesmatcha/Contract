import { afterEach, expect, test, vi } from 'vitest'

import type { AuthSession } from '@/api/types'
import {
  currentOrganizationId,
  loadSession,
  login,
  logout,
  selectCurrentOrganization,
  sessionState,
} from '@/features/auth/session'

afterEach(() => {
  localStorage.clear()
  sessionState.current = null
  sessionState.loaded = false
  vi.restoreAllMocks()
})

test('auth login stores the returned session and CSRF token', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        user: {
          id: 'user-1',
          email: 'legal@example.com',
          display_name: '李法务',
          status: 'active',
          is_platform_admin: false,
        },
        organizations: [],
        csrf_token: 'csrf_test',
      }),
      { status: 200 },
    ),
  )

  await login('legal@example.com', 'correct-horse-battery')

  expect(sessionState.current?.user.email).toBe('legal@example.com')
  expect(sessionState.current?.csrf_token).toBe('csrf_test')
})

test('current organization is validated and restored across session reloads', async () => {
  const multiOrganizationSession: AuthSession = {
    user: {
      id: 'user-2',
      email: 'multi@example.com',
      display_name: '多组织用户',
      status: 'active',
      is_platform_admin: false,
    },
    memberships: [
      {
        organization_id: 'org-1',
        organization_name: '组织一',
        role: 'reviewer',
        status: 'active',
      },
      {
        organization_id: 'org-2',
        organization_name: '组织二',
        role: 'org_admin',
        status: 'active',
      },
    ],
    csrf_token: 'csrf-multi',
  }
  sessionState.current = multiOrganizationSession
  sessionState.loaded = true

  expect(selectCurrentOrganization('outside-organization')).toBe(false)
  expect(selectCurrentOrganization('org-2')).toBe(true)
  expect(currentOrganizationId.value).toBe('org-2')

  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify(multiOrganizationSession), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  await logout()
  expect(currentOrganizationId.value).toBe('')
  await loadSession()
  expect(currentOrganizationId.value).toBe('org-2')
})
