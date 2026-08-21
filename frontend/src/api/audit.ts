import { apiFetch } from '@/api/client'
import type { AuditLogPage, AuditLogQuery } from '@/api/types'

const API_BASE = '/api/v1'

function buildQuery(options: AuditLogQuery): string {
  const query = new URLSearchParams()
  if (options.organizationFilter) query.set('organization_id', options.organizationFilter)
  if (options.action) query.set('action', options.action)
  if (options.resourceType) query.set('resource_type', options.resourceType)
  if (options.actorId) query.set('actor_id', options.actorId)
  if (options.createdFrom) query.set('created_from', options.createdFrom)
  if (options.createdTo) query.set('created_to', options.createdTo)
  if (options.limit) query.set('limit', String(options.limit))
  if (options.cursor) query.set('cursor', options.cursor)
  const suffix = query.toString()
  return suffix ? `?${suffix}` : ''
}

export function listOrganizationAuditLogs(options: AuditLogQuery = {}): Promise<AuditLogPage> {
  const headers = options.organizationId ? { 'X-Organization-ID': options.organizationId } : undefined
  return apiFetch(`${API_BASE}/audit-logs${buildQuery(options)}`, { headers })
}

export function listPlatformAuditLogs(options: AuditLogQuery = {}): Promise<AuditLogPage> {
  return apiFetch(`${API_BASE}/platform/audit-logs${buildQuery(options)}`)
}
