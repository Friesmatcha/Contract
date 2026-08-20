import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type {
  CreateReviewTaskRequest,
  ReviewTask,
  RetryReviewTaskRequest,
  RetryReviewTaskResponse,
  ReviewResults,
} from '@/api/types'

const API_BASE = '/api/v1'

export type ReviewApiErrorCode =
  | 'ACTIVE_REVIEW_EXISTS'
  | 'CONCURRENCY_LIMIT_EXCEEDED'
  | 'CONTRACT_ARCHIVED'
  | 'CONTRACT_FILE_NOT_FOUND'
  | 'CONTRACT_FILE_NOT_READY'
  | 'DOCUMENT_NOT_FOUND'
  | 'DOCUMENT_NOT_READY'
  | 'EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED'
  | 'INPUT_VERSION_CHANGED'
  | 'INVALID_STATE_TRANSITION'
  | 'REVIEW_TASK_NOT_FOUND'
  | 'RESULTS_NOT_READY'
  | 'VERSION_NOT_PUBLISHED'

function reviewTaskPath(reviewTaskId: string): string {
  return `${API_BASE}/review-tasks/${encodeURIComponent(reviewTaskId)}`
}

export function isReviewApiError<Code extends ReviewApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function createReviewTask(
  contractId: string,
  body: CreateReviewTaskRequest,
  idempotencyKey: string,
): Promise<ReviewTask> {
  return apiFetch(`${API_BASE}/contracts/${encodeURIComponent(contractId)}/reviews`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getReviewTask(
  reviewTaskId: string,
  includeStageRuns = true,
): Promise<ReviewTask> {
  const query = includeStageRuns ? '?include_stage_runs=true' : ''
  return apiFetch(`${reviewTaskPath(reviewTaskId)}${query}`)
}

export function retryReviewTask(
  reviewTaskId: string,
  body: RetryReviewTaskRequest,
  idempotencyKey: string,
): Promise<RetryReviewTaskResponse> {
  return apiFetch(`${reviewTaskPath(reviewTaskId)}/retry`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getReviewResults(
  reviewTaskId: string,
  includeEvidence = true,
): Promise<ReviewResults> {
  const query = new URLSearchParams({ include_evidence: String(includeEvidence) })
  return apiFetch(`${reviewTaskPath(reviewTaskId)}/results?${query.toString()}`)
}
