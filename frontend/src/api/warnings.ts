import { apiFetch } from '@/api/client'
import type {
  NotificationListQuery,
  NotificationPage,
  NotificationReadResponse,
  WarningDetail,
  WarningEventRequest,
  WarningEvent,
  WarningListQuery,
  WarningPage,
} from '@/api/types'

const API_BASE = '/api/v1'

function organizationHeaders(organizationId: string): HeadersInit {
  return { 'X-Organization-ID': organizationId }
}

function appendQuery(path: string, query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const encoded = params.toString()
  return encoded ? `${path}?${encoded}` : path
}

export function listWarnings(organizationId: string, query: WarningListQuery = {}): Promise<WarningPage> {
  return apiFetch(appendQuery(`${API_BASE}/warnings`, {
    status: query.status,
    severity: query.severity,
    contract_type: query.contract_type,
    assignee_id: query.assignee_id,
    risk_type: query.risk_type,
    triggered_from: query.triggered_from,
    triggered_to: query.triggered_to,
    sort: query.sort,
    direction: query.direction,
    limit: query.limit,
    cursor: query.cursor,
  }), { headers: organizationHeaders(organizationId) })
}

export function getWarning(warningId: string, organizationId: string): Promise<WarningDetail> {
  return apiFetch(`${API_BASE}/warnings/${encodeURIComponent(warningId)}`, {
    headers: organizationHeaders(organizationId),
  })
}

export function createWarningEvent(
  warningId: string,
  organizationId: string,
  body: WarningEventRequest,
): Promise<WarningEvent> {
  return apiFetch(`${API_BASE}/warnings/${encodeURIComponent(warningId)}/events`, {
    method: 'POST',
    headers: organizationHeaders(organizationId),
    body: JSON.stringify(body),
  })
}

export function listNotifications(query: NotificationListQuery = {}): Promise<NotificationPage> {
  return apiFetch(appendQuery(`${API_BASE}/notifications`, {
    status: query.status,
    warning_id: query.warning_id,
    limit: query.limit,
    cursor: query.cursor,
  }))
}

export function markNotificationRead(notificationId: string): Promise<NotificationReadResponse> {
  return apiFetch(`${API_BASE}/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function getUnreadNotificationCount(): Promise<{ unread_count: number }> {
  return apiFetch(`${API_BASE}/notifications/unread-count`)
}
