import { computed, reactive } from 'vue'

import { ApiError, apiFetch } from '@/api/client'
import type { AuthSession, LoginResponse } from '@/api/types'
import { setCsrfToken } from '@/features/auth/csrf'

export const sessionState = reactive<{
  current: AuthSession | null
  loaded: boolean
}>({ current: null, loaded: false })

const CURRENT_ORGANIZATION_STORAGE_KEY = 'contract.currentOrganizationId'
const organizationContext = reactive<{ organizationId: string | null }>({
  organizationId: null,
})

export const activeOrganizationMemberships = computed(
  () => sessionState.current?.memberships.filter((membership) => membership.status === 'active') ?? [],
)

export const currentOrganizationId = computed(() => {
  const selected = organizationContext.organizationId
  if (
    selected &&
    activeOrganizationMemberships.value.some(
      (membership) => membership.organization_id === selected,
    )
  ) {
    return selected
  }
  return activeOrganizationMemberships.value.length === 1
    ? activeOrganizationMemberships.value[0]?.organization_id ?? ''
    : ''
})

export const currentOrganizationMembership = computed(() =>
  activeOrganizationMemberships.value.find(
    (membership) => membership.organization_id === currentOrganizationId.value,
  ),
)

function storedOrganizationId(): string | null {
  try {
    return localStorage.getItem(CURRENT_ORGANIZATION_STORAGE_KEY)
  } catch {
    return null
  }
}

function rememberOrganizationId(organizationId: string): void {
  try {
    localStorage.setItem(CURRENT_ORGANIZATION_STORAGE_KEY, organizationId)
  } catch {
    // Browsers can deny storage while still allowing the authenticated session.
  }
}

export function selectCurrentOrganization(organizationId: string): boolean {
  const available = activeOrganizationMemberships.value.some(
    (membership) => membership.organization_id === organizationId,
  )
  if (!available) return false
  organizationContext.organizationId = organizationId
  rememberOrganizationId(organizationId)
  return true
}

export function defaultLandingPath(session: AuthSession): string {
  if (session.user.is_platform_admin) return '/platform/organizations'
  const currentMembership = session.memberships.find(
    (membership) =>
      membership.status === 'active' &&
      membership.organization_id === currentOrganizationId.value,
  )
  return currentMembership?.role === 'org_admin'
    ? `/organizations/${currentMembership.organization_id}/settings`
    : '/'
}

function applySession(session: AuthSession | null): void {
  sessionState.current = session
  sessionState.loaded = true
  setCsrfToken(session?.csrf_token ?? null)
  if (!session) {
    organizationContext.organizationId = null
    return
  }
  const activeIds = new Set(
    session.memberships
      .filter((membership) => membership.status === 'active')
      .map((membership) => membership.organization_id),
  )
  const selected = [organizationContext.organizationId, storedOrganizationId()].find(
    (organizationId): organizationId is string =>
      typeof organizationId === 'string' && activeIds.has(organizationId),
  )
  const activeMemberships = session.memberships.filter((membership) => membership.status === 'active')
  organizationContext.organizationId =
    selected ?? (activeMemberships.length === 1 ? activeMemberships[0]?.organization_id ?? null : null)
  if (organizationContext.organizationId) {
    rememberOrganizationId(organizationContext.organizationId)
  }
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
