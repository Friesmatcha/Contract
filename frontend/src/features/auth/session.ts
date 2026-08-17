import { reactive } from 'vue'

import { ApiError, apiFetch } from '@/api/client'
import type { AuthSession, LoginResponse } from '@/api/types'
import { setCsrfToken } from '@/features/auth/csrf'

export const sessionState = reactive<{
  current: AuthSession | null
  loaded: boolean
}>({ current: null, loaded: false })

function applySession(session: AuthSession | null): void {
  sessionState.current = session
  sessionState.loaded = true
  setCsrfToken(session?.csrf_token ?? null)
}

export async function loadSession(): Promise<AuthSession | null> {
  try {
    const session = await apiFetch<AuthSession>('/api/v1/auth/session')
    applySession(session)
    return session
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      applySession(null)
      return null
    }
    throw error
  }
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const response = await apiFetch<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  const session: AuthSession = {
    user: response.user,
    memberships: response.organizations.map((organization) => ({
      organization_id: organization.id,
      organization_name: organization.name,
      role: organization.role,
      status: 'active',
    })),
    csrf_token: response.csrf_token,
  }
  applySession(session)
  return session
}

export async function logout(): Promise<void> {
  await apiFetch<void>('/api/v1/auth/logout', { method: 'POST' })
  applySession(null)
}
