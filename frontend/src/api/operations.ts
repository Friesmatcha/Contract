import { apiFetch } from '@/api/client'
import type { ContractType, ReviewMetrics, WarningMetrics } from '@/api/types'

const API_BASE = '/api/v1'

function metricQuery(from: string, to: string): URLSearchParams {
  const query = new URLSearchParams({ from, to })
  return query
}

export function getReviewMetrics(options: {
  organizationId: string
  from: string
  to: string
  contractType?: ContractType
}): Promise<ReviewMetrics> {
  const query = metricQuery(options.from, options.to)
  if (options.contractType) query.set('contract_type', options.contractType)
  return apiFetch(
    `${API_BASE}/organizations/${options.organizationId}/metrics/reviews?${query.toString()}`,
  )
}

export function getWarningMetrics(options: {
  organizationId: string
  from: string
  to: string
  riskType?: string
  severity?: 'high' | 'medium' | 'low'
}): Promise<WarningMetrics> {
  const query = metricQuery(options.from, options.to)
  if (options.riskType) query.set('risk_type', options.riskType)
  if (options.severity) query.set('severity', options.severity)
  return apiFetch(
    `${API_BASE}/organizations/${options.organizationId}/metrics/warnings?${query.toString()}`,
  )
}
