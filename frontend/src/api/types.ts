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

export type ReviewStatus =
  | 'pending'
  | 'parsing'
  | 'reviewing'
  | 'pending_review'
  | 'completed'
  | 'failed'
  | 'archived'

export type ReviewStage =
  | 'parsing'
  | 'classification'
  | 'extraction'
  | 'risk_analysis'
  | 'clause_comparison'
  | 'report'

export type ReviewStageStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'retryable'

export interface ReviewStageRun {
  id: string
  stage: ReviewStage
  status: ReviewStageStatus
  attempt_no: number
  heartbeat_at: string | null
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
}

export interface ReviewTask {
  id: string
  display_no: string
  contract_id: string
  contract_file_id: string
  document_version_id: string | null
  status: ReviewStatus
  progress: number
  current_stage: 'queued' | ReviewStage
  rule_bundle_version_id: string
  clause_template_version_id: string
  business_scenario: string
  error_code: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  completed_by: string | null
  completed_at: string | null
  stage_runs?: ReviewStageRun[]
}

export interface CreateReviewTaskRequest {
  contract_file_id: string
  document_version_id?: string
  rule_bundle_version_id?: string
  clause_template_version_id?: string
  business_scenario?: string
}

export interface RetryReviewTaskRequest {
  from_stage?: ReviewStage
}

export interface RetryReviewTaskResponse {
  review_task_id: string
  status: 'pending'
  resumed_from_stage: ReviewStage
}

export type DocumentKind = 'docx' | 'pdf' | 'image'
export type SourceKind = 'pdf_page' | 'image_page' | 'docx_paragraph' | 'docx_table_cell'

export interface SourceSpan {
  source_span_id: string
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

export type ResultStatus =
  | 'detected'
  | 'not_found'
  | 'needs_confirmation'
  | 'confirmed'
  | 'corrected'

export type ContractCategory = 'purchase' | 'sales' | 'nda' | 'outsourcing' | 'employment' | 'other'

export type ExtractedFieldKey =
  | 'parties'
  | 'signing_date'
  | 'contract_amount'
  | 'performance_period'
  | 'dispute_resolution'
  | 'payment_terms'
  | 'auto_renewal'

export interface SourceLocator {
  source_span_id: string
  document_version_id: string
  kind: 'pdf_page' | 'image_page' | 'docx_paragraph' | 'docx_table_cell'
  page_no: number | null
  paragraph_no: number | null
  table_path: string | null
  start_offset: number
  end_offset: number
  bbox: { x: number; y: number; width: number; height: number } | null
  quote: string
}

export interface ContractClassificationResult {
  id: string
  model_value: ContractCategory
  current_value: ContractCategory
  confidence: number
  status: ResultStatus
  evidence: SourceLocator[]
  version: number
  edited_by: string | null
  edited_at: string | null
  revision_id?: string
}

export interface ExtractedFieldResult {
  id: string
  field_key: ExtractedFieldKey
  model_value: unknown | null
  current_value: unknown | null
  status: ResultStatus
  confidence: number
  evidence: SourceLocator[]
  version: number
  edited_by: string | null
  edited_at: string | null
  revision_id?: string
}

export type RiskFindingStatus = 'pending_review' | 'confirmed' | 'false_positive' | 'processed'
export type RiskFindingSource = 'rule' | 'model'
export type RiskSeverity = 'high' | 'medium' | 'low'
export type ClauseComparisonStatus = 'matched' | 'deviated' | 'missing' | 'uncertain'

export interface RiskFindingResult {
  id: string
  risk_type: string
  severity: RiskSeverity
  title: string
  description: string
  basis: string
  suggestion: string
  confidence: number
  source: RiskFindingSource
  status: RiskFindingStatus
  evidence: SourceLocator[]
  version: number
  edited_by: string | null
  edited_at: string | null
  revision_id?: string
}

export interface ClauseComparisonResult {
  id: string
  clause_key: string
  status: ClauseComparisonStatus
  contract_text: string | null
  difference_summary: string | null
  severity: RiskSeverity
  suggestion: string
  evidence: SourceLocator[]
  version: number
  edited_by: string | null
  edited_at: string | null
  revision_id?: string
}

export interface ReviewResultsSummary {
  risk_total: number
  high: number
  medium: number
  low: number
  warning_total: number
  unresolved_count: number
  required_manual_count: number
}

export type ResultSubjectType = 'classification' | 'extracted_field' | 'risk_finding' | 'clause_comparison'

export interface CompletionBlocker {
  subject_type: ResultSubjectType
  subject_id: string
  code: string
  status: string
  version: number
}

export interface ReviewResults {
  review_task_id: string
  classification: ContractClassificationResult
  extracted_fields: ExtractedFieldResult[]
  risk_findings: RiskFindingResult[]
  clause_comparisons: ClauseComparisonResult[]
  summary: ReviewResultsSummary
  completion_blockers: CompletionBlocker[]
}

export interface FeedbackResponse {
  id: string
  subject_type: ResultSubjectType
  subject_id: string
  label: 'correct' | 'incorrect' | 'modified' | 'ignored'
  created_by: string
  created_at: string
}

export interface FeedbackSummary {
  filters: {
    contract_type: ContractCategory | null
    rule_bundle_version_id: string | null
    model_version: string | null
    created_from: string | null
    created_to: string | null
  }
  counts: Record<'correct' | 'incorrect' | 'modified' | 'ignored', number>
  by_risk_type: Array<{
    risk_type: string
    correct: number
    incorrect: number
    modified: number
    ignored: number
  }>
}

export type WarningStatus =
  | 'pending_confirmation'
  | 'in_progress'
  | 'ignored'
  | 'resolved'
  | 'closed'
export type WarningSeverity = 'high' | 'medium' | 'low'
export type WarningEventType =
  | 'confirm'
  | 'false_positive'
  | 'ignore'
  | 'assign'
  | 'note'
  | 'resolve'
  | 'close'
  | 'reopen'

export interface WarningListItem {
  id: string
  contract_id: string
  review_task_id: string
  severity: WarningSeverity
  status: WarningStatus
  priority: WarningSeverity
  assignee_id: string | null
  due_at: string | null
  trigger_type: string
  triggered_at: string
}

export interface WarningSummary {
  unprocessed_count: number
  high_count: number
}

export interface WarningPage extends CursorPage<WarningListItem> {
  summary: WarningSummary
}

export interface WarningAssignee {
  id: string
  display_name: string | null
  email: string
}

export interface WarningEvent {
  event_id: string
  event_type: string
  from_status: WarningStatus | null
  to_status: WarningStatus | null
  actor_id: string | null
  note: string | null
  assignee_id: string | null
  due_at: string | null
  created_at: string
}

export interface WarningDetail extends WarningListItem {
  contract_id: string
  review_task_id: string
  trigger_type: string
  triggered_at: string
  risk_finding_id: string | null
  clause_comparison_id: string | null
  extracted_field_id: string | null
  classification_id: string | null
  assignee: WarningAssignee | null
  resolution: string | null
  revision_id: string | null
  closed_at: string | null
  evidence: SourceLocator[]
  events: WarningEvent[]
}

export interface WarningListQuery {
  status?: WarningStatus
  severity?: WarningSeverity
  contract_type?: ContractType
  assignee_id?: string
  risk_type?: string
  triggered_from?: string
  triggered_to?: string
  sort?: 'triggered_at' | 'priority' | 'due_at'
  direction?: 'asc' | 'desc'
  limit?: number
  cursor?: string
}

export interface WarningEventRequest {
  type: WarningEventType
  note?: string
  assignee_id?: string
  due_at?: string | null
  resolution?: string
  revision_id?: string
}

export type NotificationStatus = 'unread' | 'read'

export interface Notification {
  id: string
  warning_id: string
  channel: 'in_app'
  status: NotificationStatus
  title: string
  body: string
  created_at: string
}

export type NotificationPage = CursorPage<Notification>

export interface NotificationListQuery {
  status?: NotificationStatus
  warning_id?: string
  limit?: number
  cursor?: string
}

export interface NotificationReadResponse {
  id: string
  status: 'read'
  read_at: string
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

export type RiskRuleEngine = 'deterministic' | 'model'
export type RiskRuleSeverity = 'high' | 'medium' | 'low'
export type RiskRuleBundleStatus = 'active' | 'disabled'
export type RiskRuleVersionStatus = 'draft' | 'published'

export type RiskRuleComparison = 'gt' | 'gte' | 'lt' | 'lte' | 'eq'
export type RiskRuleTextField = 'contract_text'
export type RiskRuleAmountField = 'contract_amount'
export type RiskRuleDateField = 'signing_date'
export type RiskRulePresenceField =
  | 'parties'
  | 'signing_date'
  | 'contract_amount'
  | 'performance_period'
  | 'dispute_resolution'
  | 'payment_terms'
  | 'auto_renewal'
  | 'acceptance_standard'
  | 'intellectual_property'
  | 'data_compliance'
  | 'force_majeure'
export type RiskRuleField =
  | RiskRuleTextField
  | RiskRuleAmountField
  | RiskRuleDateField
  | RiskRulePresenceField

export type RiskRuleCondition =
  | { operator: 'keyword'; field: RiskRuleTextField; value: string }
  | { operator: 'regex'; field: RiskRuleTextField; pattern: string }
  | {
      operator: 'amount_threshold'
      field: RiskRuleAmountField
      comparison: RiskRuleComparison
      value: string
    }
  | {
      operator: 'date_threshold'
      field: RiskRuleDateField
      comparison: RiskRuleComparison
      value: string
    }
  | { operator: 'field_exists' | 'field_missing'; field: RiskRulePresenceField }
  | { operator: 'semantic' }
  | { operator: 'all' | 'any'; conditions: RiskRuleCondition[] }
  | { operator: 'not'; condition: RiskRuleCondition }

export interface RiskRuleInput {
  rule_key: string
  risk_type: string
  engine: RiskRuleEngine
  condition: RiskRuleCondition
  severity: RiskRuleSeverity
  suggestion: string
  enabled: boolean
}

export interface RiskRule extends RiskRuleInput {
  id: string
}

export interface RiskRuleBundle {
  id: string
  organization_id: string
  name: string
  status: RiskRuleBundleStatus
  current_published_version_id: string | null
  is_default: boolean
  version: number
}

export interface RiskRuleVersionSummary {
  id: string
  organization_id: string
  version_no: number
  status: RiskRuleVersionStatus
  change_note: string
  effective_at: string | null
  published_by: string | null
  rule_count: number
  rules?: RiskRule[]
}

export interface RiskRuleBundleDetail extends RiskRuleBundle {
  versions: RiskRuleVersionSummary[]
}

export interface RiskRuleVersion {
  id: string
  organization_id: string
  bundle_id: string
  version_no: number
  status: RiskRuleVersionStatus
  change_note: string
  effective_at: string | null
  published_by: string | null
  version: number
  is_default: boolean
  current_published_version_id: string | null
  rules: RiskRule[]
}

export interface RiskRuleListQuery {
  status?: RiskRuleBundleStatus
  q?: string
  limit?: number
  cursor?: string
}

export interface CreateRiskRuleBundleRequest {
  name: string
}

export interface UpdateRiskRuleBundleRequest {
  name?: string
  status?: RiskRuleBundleStatus
  is_default?: boolean
  version: number
}

export interface CreateRiskRuleVersionRequest {
  change_note: string
  source_version_id?: string
  rules: RiskRuleInput[]
}

export interface UpdateRiskRuleVersionRequest {
  rules?: RiskRuleInput[]
  change_note?: string
  version: number
}

export type ClauseContractType = Exclude<ContractType, 'other'>
export type ClauseTemplateStatus = 'active' | 'disabled'
export type ClauseTemplateVersionStatus = 'draft' | 'published'
export type ClauseSeverity = 'high' | 'medium' | 'low'

export interface StandardClauseInput {
  clause_key: string
  name: string
  standard_text: string
  allowed_deviation: string
  severity: ClauseSeverity
  applicability: Record<string, unknown>
  suggestion: string
  enabled: boolean
  order_no: number
}

export interface StandardClause extends StandardClauseInput {
  id: string
}

export interface ClauseTemplate {
  organization_id: string
  id: string
  name: string
  contract_type: ClauseContractType
  business_scenario: string
  status: ClauseTemplateStatus
  current_published_version_id: string | null
  is_default: boolean
  version: number
}

export interface ClauseTemplateVersionSummary {
  organization_id: string
  id: string
  version_no: number
  status: ClauseTemplateVersionStatus
  change_note: string
  effective_at: string | null
  published_by: string | null
  clauses?: StandardClause[]
}

export interface ClauseTemplateDetail extends ClauseTemplate {
  versions: ClauseTemplateVersionSummary[]
}

export interface ClauseTemplateVersion {
  organization_id: string
  id: string
  template_id: string
  version_no: number
  status: ClauseTemplateVersionStatus
  change_note: string
  effective_at: string | null
  published_by: string | null
  version: number
  is_default: boolean
  current_published_version_id: string | null
  clauses: StandardClause[]
}

export interface ClauseTemplateListQuery {
  contract_type?: ClauseContractType
  business_scenario?: string
  status?: ClauseTemplateStatus
  q?: string
  limit?: number
  cursor?: string
}

export interface CreateClauseTemplateRequest {
  name: string
  contract_type: ClauseContractType
  business_scenario?: string
}

export interface UpdateClauseTemplateRequest {
  name?: string
  business_scenario?: string
  status?: ClauseTemplateStatus
  is_default?: boolean
  version: number
}

export interface CreateClauseTemplateVersionRequest {
  change_note: string
  source_version_id?: string
  clauses: StandardClauseInput[]
}

export interface UpdateClauseTemplateVersionRequest {
  clauses?: StandardClauseInput[]
  change_note?: string
  version: number
}
