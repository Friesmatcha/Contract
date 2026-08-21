import { apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import type { Report, ReportCreateResponse, ReportFormat } from '@/api/types'

const API_BASE = '/api/v1'

export type ReportApiErrorCode =
  | 'CONCURRENCY_LIMIT_EXCEEDED'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'REPORT_ALREADY_GENERATING'
  | 'REPORT_EXPIRED'
  | 'REPORT_NOT_FOUND'
  | 'REPORT_NOT_READY'
  | 'REPORT_RENDERER_UNAVAILABLE'
  | 'REVIEW_TASK_NOT_READY'

export function isReportApiError<Code extends ReportApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function createReport(
  reviewTaskId: string,
  format: ReportFormat,
  idempotencyKey: string,
): Promise<ReportCreateResponse> {
  return apiFetch(`${API_BASE}/review-tasks/${encodeURIComponent(reviewTaskId)}/reports`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ format }),
  })
}

export function getReport(reportId: string): Promise<Report> {
  return apiFetch(`${API_BASE}/reports/${encodeURIComponent(reportId)}`)
}

export function reportDownloadUrl(reportId: string, disposition: 'attachment' | 'inline' = 'attachment'): string {
  const query = new URLSearchParams({ disposition })
  return `${API_BASE}/reports/${encodeURIComponent(reportId)}/download?${query.toString()}`
}
