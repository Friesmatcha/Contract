import type { SafeDisplayError } from '@/api/types'

export interface ApiErrorPayload {
  error: {
    code: string
    message: string
    request_id: string
    details?: Record<string, unknown>
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string
  readonly details?: Record<string, unknown>

  constructor(status: number, payload: ApiErrorPayload, responseRequestId?: string) {
    super(payload.error.message)
    this.name = 'ApiError'
    this.status = status
    this.code = payload.error.code
    this.requestId = responseRequestId || payload.error.request_id
    this.details = payload.error.details
  }
}

export class ApiClientError extends Error {
  readonly status: number
  readonly requestId?: string

  constructor(status: number, message: string, requestId?: string) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.requestId = requestId
  }
}

function isApiErrorPayload(value: unknown): value is ApiErrorPayload {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = value.error
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string' &&
    'request_id' in error &&
    typeof error.request_id === 'string'
  )
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, {
    ...init,
    credentials: 'include',
    headers,
  })
  const responseRequestId = response.headers.get('X-Request-ID') || undefined

  if (response.status === 204) return undefined as T

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiClientError(response.status, '服务返回了无法识别的响应。', responseRequestId)
  }
  if (!response.ok) {
    if (isApiErrorPayload(body)) throw new ApiError(response.status, body, responseRequestId)
    throw new ApiClientError(response.status, '服务返回了无法识别的错误。', responseRequestId)
  }
  return body as T
}

export function toSafeDisplayError(error: unknown): SafeDisplayError {
  if (error instanceof ApiError || error instanceof ApiClientError) {
    return { message: error.message, requestId: error.requestId }
  }
  return { message: '请求未能完成，请稍后重试。' }
}
