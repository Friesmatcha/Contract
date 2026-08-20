import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import { createReviewTask, getReviewTask, retryReviewTask } from '@/api/reviews'
import { setCsrfToken } from '@/features/auth/csrf'
import ReviewCreatePage from '@/pages/reviews/ReviewCreatePage.vue'
import ReviewProgressPage from '@/pages/reviews/ReviewProgressPage.vue'
import type { AuthSession } from '@/api/types'
import { sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  sessionState.current = null
  sessionState.loaded = false
  vi.restoreAllMocks()
  setCsrfToken(null)
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function renderAt(
  component: object,
  path: string,
  routes: Array<{ path: string; component: object }>,
) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return { router, ...render(component, { global: { plugins: [router, ElementPlus] } }) }
}

const currentSession: AuthSession = {
  user: {
    id: 'user-1',
    email: 'reviewer@example.com',
    display_name: '审核员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [
    {
      organization_id: 'org-1',
      organization_name: '示例企业',
      role: 'reviewer',
      status: 'active',
    },
  ],
  csrf_token: 'csrf-review',
}

const task = {
  id: 'task-1',
  display_no: 'REV-20260820-000001',
  contract_id: 'contract-1',
  contract_file_id: 'file-1',
  document_version_id: null,
  status: 'pending' as const,
  progress: 0,
  current_stage: 'queued' as const,
  rule_bundle_version_id: 'rule-version-1',
  clause_template_version_id: 'template-version-1',
  business_scenario: 'standard',
  error_code: null,
  error_message: null,
  created_at: '2026-08-20T00:00:00Z',
  started_at: null,
  finished_at: null,
  stage_runs: [],
}

test('review API maps create, status and retry routes with CSRF/idempotency headers', async () => {
  setCsrfToken('csrf-review')
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() => Promise.resolve(response(task, 202)))

  await createReviewTask('contract/1', { contract_file_id: 'file/1' }, 'create-review')
  await getReviewTask('task/1')
  await retryReviewTask('task/1', {}, 'retry-review')

  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    '/api/v1/contracts/contract%2F1/reviews',
    '/api/v1/review-tasks/task%2F1?include_stage_runs=true',
    '/api/v1/review-tasks/task%2F1/retry',
  ])
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Idempotency-Key')).toBe(
    'create-review',
  )
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-CSRF-Token')).toBe(
    'csrf-review',
  )
  expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('Idempotency-Key')).toBe(
    'retry-review',
  )
})

test('create review page selects a validated file and navigates to progress', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
    '00000000-0000-4000-8000-000000000001',
  )
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({
      id: 'contract-1',
      display_no: 'CTR-0001',
      title: '采购合同',
      declared_type: 'purchase',
      status: 'active',
      owner_id: 'user-1',
      current_file: null,
      files: [{
        id: 'file-1',
        version_no: 1,
        is_current: true,
        original_name: 'contract.pdf',
        scan_status: 'clean',
        storage_status: 'stored',
        external_model_notice_acknowledged_at: '2026-08-20T00:00:00Z',
      }],
      latest_review: null,
      created_at: '2026-08-20T00:00:00Z',
      updated_at: '2026-08-20T00:00:00Z',
      version: 1,
    }))
    .mockResolvedValueOnce(response({ items: [], next_cursor: null, has_more: false }))
    .mockResolvedValueOnce(response({ items: [], next_cursor: null, has_more: false }))
    .mockResolvedValueOnce(response(task, 202))

  const { router } = await renderAt(ReviewCreatePage, '/contracts/contract-1/reviews/new', [
    { path: '/contracts/:contractId/reviews/new', component: ReviewCreatePage },
    { path: '/reviews/:reviewTaskId', component: ReviewProgressPage },
  ])

  await waitFor(() => expect(screen.getByRole('button', { name: '创建审核任务' })).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '创建审核任务' }))

  await waitFor(() => expect(router.currentRoute.value.path).toBe('/reviews/task-1'))
  expect(fetchMock).toHaveBeenCalledTimes(4)
  expect(JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body))).toEqual({
    contract_file_id: 'file-1',
    business_scenario: 'standard',
  })
})

test('review progress shows safe failure and retries only for writer roles', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
    '00000000-0000-4000-8000-000000000002',
  )
  const failedTask = {
    ...task,
    status: 'failed' as const,
    progress: 17,
    current_stage: 'parsing' as const,
    error_code: 'STAGE_EXECUTION_FAILED',
    error_message: '阶段执行失败，请重试。',
    stage_runs: [{
      id: 'run-1',
      stage: 'parsing' as const,
      status: 'failed' as const,
      attempt_no: 1,
      heartbeat_at: null,
      started_at: '2026-08-20T00:00:00Z',
      finished_at: '2026-08-20T00:00:01Z',
      error_code: 'STAGE_EXECUTION_FAILED',
      error_message: '阶段执行失败，请重试。',
    }],
  }
  const fetchMock = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(failedTask))
    .mockResolvedValueOnce(response({ title: '采购合同' }))
    .mockResolvedValueOnce(response({ ...task, status: 'pending' }, 202))
    .mockResolvedValueOnce(response(task))

  await renderAt(ReviewProgressPage, '/reviews/task-1', [
    { path: '/reviews/:reviewTaskId', component: ReviewProgressPage },
  ])
  await waitFor(() => expect(screen.getByRole('heading', { name: '审核失败' })).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '重试失败阶段' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
  expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({})
  expect(new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('Idempotency-Key')).toBe(
    '00000000-0000-4000-8000-000000000002',
  )
})
