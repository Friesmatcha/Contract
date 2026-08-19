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

export type ContractType = 'purchase' | 'sales' | 'nda' | 'outsourcing' | 'employment' | 'other'

export type ContractStatus = 'active' | 'archived'

export interface ContractFileSummary {
  id: string
  version_no: number
  is_current: boolean
  original_name?: string | null
  media_type?: string | null
  size_bytes?: number | null
  scan_status?: 'pending' | 'clean' | 'infected' | 'failed' | null
  storage_status?: 'quarantine' | 'stored' | 'failed' | null
  created_at?: string | null
  external_model_notice_acknowledged_at?: string | null
}

export interface FileObject {
  id: string
  original_name: string
  media_type: string
  size_bytes: number
  sha256: string
  scan_status: 'pending' | 'clean' | 'infected' | 'failed'
  storage_status: 'quarantine' | 'stored' | 'failed'
  created_at: string
}

export interface ContractFileUploadResponse {
  file: FileObject
  contract_file_id: string
  version_no: number
  is_current: boolean
  external_model_notice_acknowledged_at: string
}

export interface LatestReviewSummary {
  id: string
  status: string
}

export interface Contract {
  id: string
  display_no: string
  title: string
  declared_type: ContractType | null
  status: ContractStatus
  owner_id: string
  current_file: ContractFileSummary | null
  files: ContractFileSummary[]
  latest_review: LatestReviewSummary | null
  created_at: string
  updated_at: string
  version: number
}

export interface ContractListQuery {
  q?: string
  status?: ContractStatus
  declared_type?: ContractType
  owner_id?: string
  sort?: 'created_at' | 'updated_at' | 'title'
  direction?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface CreateContractRequest {
  title: string
  declared_type?: ContractType
}

export interface UpdateContractRequest {
  title?: string
  declared_type?: ContractType | null
  version: number
}

export interface ContractStatusResponse {
  id: string
  status: ContractStatus
  archived_at: string | null
}

export interface ContractAccessGrant {
  contract_id: string
  user_id: string
  access_level: 'read'
}

export type DocumentKind = 'docx' | 'pdf' | 'image'
export type SourceKind = 'pdf_page' | 'image_page' | 'docx_paragraph' | 'docx_table_cell'

export interface SourceSpan {
  document_version_id: string
  kind: SourceKind
  page_no: number | null
  paragraph_no: number | null
  table_path: string | null
  start_offset: number
  end_offset: number
  bbox: { x: number; y: number; width: number; height: number } | null
  quote: string
}

export interface DocumentBlock {
  id: string
  order_no: number
  block_type: string
  page_no: number | null
  paragraph_no: number | null
  table_path: string | null
  text: string
  bbox: { x: number; y: number; width: number; height: number } | null
  source_spans: SourceSpan[]
}

export interface DocumentPageResponse {
  document_version_id: string
  document_kind: DocumentKind
  page_no: number
  page_count: number
  width: number | null
  height: number | null
  text: string
  image_file_id: string | null
  ocr_status: string
  ocr_confidence: number | null
  error_code: string | null
  error_message: string | null
  blocks: DocumentBlock[]
}

export interface DocumentBlocksResponse {
  document_version_id: string
  document_kind: DocumentKind
  page_count: number
  blocks: DocumentBlock[]
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
