export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

export interface SafeDisplayError {
  message: string
  requestId?: string
}

export interface SessionUser {
  id: string
  email: string
  display_name: string
  status: string
  is_platform_admin: boolean
}

export interface SessionMembership {
  organization_id: string
  organization_name: string
  role: 'org_admin' | 'reviewer' | 'viewer'
  status: 'active' | 'pending_invitation' | 'disabled'
}

export interface AuthSession {
  user: SessionUser
  memberships: SessionMembership[]
  csrf_token: string
}

export interface LoginResponse {
  user: SessionUser
  organizations: Array<Pick<SessionMembership, 'role'> & { id: string; name: string }>
  csrf_token: string
}
