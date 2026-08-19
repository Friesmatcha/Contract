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

export type OrganizationStatus = 'active' | 'disabled'

export type OrganizationRole = 'org_admin' | 'reviewer' | 'viewer'

export type MembershipRole = OrganizationRole

export type MembershipStatus = 'pending_invitation' | 'active' | 'disabled'

export type InvitationDeliveryStatus = 'queued' | 'sent' | 'failed'

export interface OrganizationSettings {
  file_size_limit_bytes: number
  page_limit: number
  concurrent_review_limit: number
  warn_on_medium_risk: boolean
  ocr_low_confidence_threshold: number
  retention_days: number
  report_watermark: string
  version: number
}

export interface Organization {
  id: string
  name: string
  status: OrganizationStatus
  retention_days: number
  settings: Omit<OrganizationSettings, 'version'>
  version: number
  created_at: string
  updated_at: string
}

export interface PlatformOrganizationListItem {
  id: string
  name: string
  status: OrganizationStatus
  retention_days: number
  created_at: string
}

export interface PlatformOrganizationListQuery {
  q?: string
  status?: OrganizationStatus
  sort?: 'created_at' | 'name'
  direction?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface CreateOrganizationRequest {
  name: string
  initial_admin_email: string
  retention_days?: number
}

export interface UpdateOrganizationRequest {
  name?: string
  status?: OrganizationStatus
  retention_days?: number
  version: number
}

export interface OrganizationProfile {
  id: string
  name: string
  status: OrganizationStatus
  my_role: OrganizationRole
  permissions: string[]
}

export interface UpdateOrganizationSettingsRequest {
  file_size_limit_bytes?: number
  page_limit?: number
  concurrent_review_limit?: number
  warn_on_medium_risk?: boolean
  ocr_low_confidence_threshold?: number
  retention_days?: number
  report_watermark?: string
  version: number
}

export interface Membership {
  id: string
  user_id: string | null
  email: string
  display_name: string | null
  role: MembershipRole
  status: MembershipStatus
  invited_at: string | null
  email_delivery_status: InvitationDeliveryStatus | null
  version: number
  created_at: string
  updated_at: string
}

export interface OrganizationMemberListQuery {
  q?: string
  role?: MembershipRole
  status?: MembershipStatus
  sort?: 'created_at' | 'display_name'
  direction?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface InviteMemberRequest {
  email: string
  role: MembershipRole
}

export interface UpdateMemberRequest {
  role?: MembershipRole
  status?: 'active' | 'disabled'
  version: number
}

export type SupportAccessGrantStatus = 'active' | 'expired' | 'revoked'

export interface SupportAccessGrant {
  id: string
  organization_id: string
  platform_admin_user_id: string
  reason: string
  status: SupportAccessGrantStatus
  granted_by: string
  created_at: string
  expires_at: string
}

export interface SupportAccessGrantListQuery {
  status?: SupportAccessGrantStatus
  platform_admin_user_id?: string
  sort?: 'created_at' | 'expires_at'
  direction?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface CreateSupportAccessGrantRequest {
  platform_admin_user_id: string
  reason: string
  expires_at: string
}

export interface PlatformModelConfiguration {
  provider: string
  model: string
  model_source: 'environment'
  timeout_seconds: number
  max_retries: number
  hard_budget_enabled: false
  usage_tracking_enabled: boolean
  organization_overrides_allowed: false
  secret_configured: boolean
  status: OrganizationStatus
  version: number
}

export interface UpdatePlatformModelConfigurationRequest {
  timeout_seconds?: number
  max_retries?: number
  usage_tracking_enabled?: boolean
  status?: OrganizationStatus
  version: number
}
