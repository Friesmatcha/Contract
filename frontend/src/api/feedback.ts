import { apiFetch } from '@/api/client'
import type { FeedbackResponse, FeedbackSummary, ResultSubjectType } from '@/api/types'

const API_BASE = '/api/v1'

export function createFeedback(
  body: {
    review_task_id: string
    subject_type: ResultSubjectType
    subject_id: string
    label: 'correct' | 'incorrect' | 'modified' | 'ignored'
    corrected_value?: unknown
    note?: string
  },
  idempotencyKey: string,
): Promise<FeedbackResponse> {
  return apiFetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getFeedbackSummary(options: {
  contractType?: string
  ruleBundleVersionId?: string
  modelVersion?: string
  createdFrom?: string
  createdTo?: string
  organizationId?: string
} = {}): Promise<FeedbackSummary> {
  const query = new URLSearchParams()
  if (options.contractType) query.set('contract_type', options.contractType)
  if (options.ruleBundleVersionId) query.set('rule_bundle_version_id', options.ruleBundleVersionId)
  if (options.modelVersion) query.set('model_version', options.modelVersion)
  if (options.createdFrom) query.set('created_from', options.createdFrom)
  if (options.createdTo) query.set('created_to', options.createdTo)
  const suffix = query.toString()
  const headers = options.organizationId ? { 'X-Organization-ID': options.organizationId } : undefined
  return apiFetch(`${API_BASE}/feedback/summary${suffix ? `?${suffix}` : ''}`, { headers })
}
