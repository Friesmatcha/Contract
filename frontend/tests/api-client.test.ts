import { ApiError, apiFetch } from '@/api/client'
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
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    ),
  )

  const request = apiFetch('/api/v1/health/ready')

  await expect(request).rejects.toMatchObject({
    status: 503,
    code: 'SERVICE_NOT_READY',
    requestId: 'req_test',
  } satisfies Partial<ApiError>)
})

test('replaces non-JSON gateway errors with a safe message', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('<html>upstream failed</html>', {
      status: 502,
      headers: { 'Content-Type': 'text/html' },
    }),
  )

  await expect(apiFetch('/api/v1/health/ready')).rejects.toThrow(
    '服务返回了无法识别的响应。',
  )
})
