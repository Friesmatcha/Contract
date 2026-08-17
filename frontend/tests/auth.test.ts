import { expect, test, vi } from 'vitest'

import { login, sessionState } from '@/features/auth/session'

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
