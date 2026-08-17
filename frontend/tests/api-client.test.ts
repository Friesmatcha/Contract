import { ApiClientError, ApiError, apiFetch, toSafeDisplayError } from '@/api/client'
import type { CursorPage } from '@/api/types'
import { setCsrfToken } from '@/features/auth/csrf'
import { expect, test, vi } from 'vitest'

test('always includes browser credentials', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

  await apiFetch<{ status: string }>('/api/v1/health/live')

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/health/live',
    expect.objectContaining({ credentials: 'include' }),
  )
})

test('adds the current CSRF token to unsafe requests', async () => {
  setCsrfToken('csrf_test')
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ accepted: true }), { status: 200 }),
  )

  await apiFetch('/api/v1/auth/logout', { method: 'POST' })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/auth/logout',
    expect.objectContaining({
      headers: expect.objectContaining({ get: expect.any(Function) }),
    }),
  )
  const requestHeaders = fetchMock.mock.calls.at(0)?.[1]?.headers as Headers
  expect(requestHeaders.get('X-CSRF-Token')).toBe('csrf_test')
})

test('parses the shared API error shape', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        error: {
          code: 'SERVICE_NOT_READY',
          message: '服务尚未就绪。',
          request_id: 'req_test',
        },
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req_header' },
      },
    ),
  )

  const request = apiFetch('/api/v1/health/ready')

  await expect(request).rejects.toMatchObject({
    status: 503,
    code: 'SERVICE_NOT_READY',
    requestId: 'req_header',
  } satisfies Partial<ApiError>)
})

test('replaces non-JSON gateway errors with a safe message', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('<html>upstream failed</html>', {
      status: 502,
      headers: { 'Content-Type': 'text/html', 'X-Request-ID': 'req_gateway' },
    }),
  )

  await expect(apiFetch('/api/v1/health/ready')).rejects.toMatchObject({
    message: '服务返回了无法识别的响应。',
    requestId: 'req_gateway',
  } satisfies Partial<ApiClientError>)
})

test('exposes only safe display fields for unknown errors', () => {
  expect(toSafeDisplayError(new Error('postgresql://user:secret@internal/db'))).toEqual({
    message: '请求未能完成，请稍后重试。',
  })
})

test('defines the contract cursor page shape', () => {
  const page: CursorPage<{ id: string }> = {
    items: [{ id: 'one' }],
    next_cursor: null,
    has_more: false,
  }

  expect(page.items).toHaveLength(1)
})
