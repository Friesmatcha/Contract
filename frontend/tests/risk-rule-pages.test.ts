import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import type { AuthSession } from '@/api/types'
import RiskRuleBundleDetailPage from '@/pages/risks/RiskRuleBundleDetailPage.vue'
import RiskRuleBundleListPage from '@/pages/risks/RiskRuleBundleListPage.vue'
import RiskRuleVersionEditorPage from '@/pages/risks/RiskRuleVersionEditorPage.vue'
import {
  currentOrganizationId,
  selectCurrentOrganization,
  sessionState,
} from '@/features/auth/session'

afterEach(() => {
  cleanup()
  sessionState.current = null
  sessionState.loaded = false
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const adminSession: AuthSession = {
  user: {
    id: 'user-1',
    email: 'admin@example.com',
    display_name: '组织管理员',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [
    {
      organization_id: 'org-1',
      organization_name: '示例企业',
      role: 'org_admin',
      status: 'active',
    },
  ],
  csrf_token: 'csrf-risk',
}

function sessionWithRole(role: 'org_admin' | 'reviewer' | 'viewer'): AuthSession {
  return {
    ...adminSession,
    memberships: [{ ...adminSession.memberships[0]!, role }],
  }
}

function versionResponse(status: 'draft' | 'published' = 'draft', version = 1) {
  return {
    id: 'version-1',
    organization_id: 'org-1',
    bundle_id: 'bundle-1',
    version_no: 1,
    status,
    change_note: '初始化规则',
    effective_at: status === 'published' ? '2026-08-19T06:00:00Z' : null,
    published_by: status === 'published' ? 'user-1' : null,
    version,
    is_default: status === 'published',
    current_published_version_id: status === 'published' ? 'version-1' : null,
    rules: [
      {
        id: 'rule-1',
        rule_key: 'payment_cap',
        risk_type: 'payment_terms',
        engine: 'deterministic',
        condition: {
          operator: 'amount_threshold',
          field: 'contract_amount',
          comparison: 'gt',
          value: '30',
        },
        severity: 'high',
        suggestion: '请复核付款条件。',
        enabled: true,
      },
    ],
  }
}

async function renderAt(component: object, path: string, routes: Array<{ path: string; component: object }>) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return render(component, { global: { plugins: [router, ElementPlus] } })
}

test('risk bundle list renders the default marker and tenant-scoped request', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      items: [
        {
          id: 'bundle-1',
          organization_id: 'org-1',
          name: '采购风险基线',
          status: 'active',
          current_published_version_id: 'version-1',
          is_default: true,
          version: 1,
        },
      ],
      next_cursor: null,
      has_more: false,
    }),
  )

  await renderAt(RiskRuleBundleListPage, '/risk-rule-bundles', [
    { path: '/risk-rule-bundles', component: RiskRuleBundleListPage },
  ])

  await waitFor(() => expect(screen.getByText('采购风险基线')).toBeInTheDocument())
  expect(screen.getByText('默认')).toBeInTheDocument()
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('risk bundle list uses the explicitly selected organization', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [
      adminSession.memberships[0]!,
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'org_admin',
        status: 'active',
      },
    ],
  }
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-2')).toBe(true)
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({ items: [], next_cursor: null, has_more: false }),
  )

  await renderAt(RiskRuleBundleListPage, '/risk-rule-bundles', [
    { path: '/risk-rule-bundles', component: RiskRuleBundleListPage },
  ])

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-2')
})

test('risk bundle list ignores an old organization response', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [
      adminSession.memberships[0]!,
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'org_admin',
        status: 'active',
      },
    ],
  }
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-1')).toBe(true)
  let resolveFirst: (value: Response) => void = () => undefined
  const firstResponse = new Promise<Response>((resolve) => {
    resolveFirst = resolve
  })
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementationOnce(() => firstResponse)
    .mockResolvedValueOnce(
      response({
        items: [
        {
          id: 'bundle-2',
          organization_id: 'org-2',
          name: '第二组织规则集',
            status: 'active',
            current_published_version_id: null,
            is_default: false,
            version: 1,
          },
        ],
        next_cursor: null,
        has_more: false,
      }),
    )

  await renderAt(RiskRuleBundleListPage, '/risk-rule-bundles', [
    { path: '/risk-rule-bundles', component: RiskRuleBundleListPage },
  ])
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(selectCurrentOrganization('org-2')).toBe(true)
  await waitFor(() => expect(screen.getByText('第二组织规则集')).toBeInTheDocument())

  resolveFirst(
    response({
      items: [
        {
          id: 'bundle-1',
          organization_id: 'org-1',
          name: '第一组织旧响应',
          status: 'active',
          current_published_version_id: null,
          is_default: false,
          version: 1,
        },
      ],
      next_cursor: null,
      has_more: false,
    }),
  )
  await waitFor(() => expect(screen.queryByText('第一组织旧响应')).not.toBeInTheDocument())
})

test('risk bundle detail renders version history and current rule preview', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      id: 'bundle-1',
      organization_id: 'org-1',
      name: '采购风险基线',
      status: 'active',
      current_published_version_id: 'version-1',
      is_default: true,
      version: 2,
      versions: [
        {
          id: 'version-1',
          organization_id: 'org-1',
          version_no: 1,
          status: 'published',
          change_note: '初始化规则',
          effective_at: '2026-08-19T06:00:00Z',
          published_by: 'user-1',
          rule_count: 1,
          rules: [
            {
              id: 'rule-1',
              rule_key: 'payment_cap',
              risk_type: 'payment_terms',
              engine: 'deterministic',
              condition: { operator: 'keyword', field: 'text', value: '付款' },
              severity: 'high',
              suggestion: '请复核付款条件。',
              enabled: true,
            },
          ],
        },
      ],
    }),
  )

  await renderAt(RiskRuleBundleDetailPage, '/risk-rule-bundles/bundle-1', [
    { path: '/risk-rule-bundles/:bundleId', component: RiskRuleBundleDetailPage },
  ])

  await waitFor(() => expect(screen.getByText('采购风险基线')).toBeInTheDocument())
  expect(screen.getByText('版本历史')).toBeInTheDocument()
  expect(screen.getByText('当前版本规则预览')).toBeInTheDocument()
})

test('published risk rule version is rendered read-only', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      id: 'version-1',
      organization_id: 'org-1',
      bundle_id: 'bundle-1',
      version_no: 1,
      status: 'published',
      change_note: '初始化规则',
      effective_at: '2026-08-19T06:00:00Z',
      published_by: 'user-1',
      version: 1,
      is_default: true,
      current_published_version_id: 'version-1',
      rules: [
        {
          id: 'rule-1',
          rule_key: 'payment_cap',
          risk_type: 'payment_terms',
          engine: 'deterministic',
          condition: { operator: 'keyword', field: 'text', value: '付款' },
          severity: 'high',
          suggestion: '请复核付款条件。',
          enabled: true,
        },
      ],
    }),
  )

  await renderAt(RiskRuleVersionEditorPage, '/risk-rule-bundle-versions/version-1', [
    { path: '/risk-rule-bundle-versions/:versionId', component: RiskRuleVersionEditorPage },
  ])

  await waitFor(() => expect(screen.getByText('查看已发布规则 v1')).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: '保存草稿' })).not.toBeInTheDocument()
  expect(screen.getByText('已发布')).toBeInTheDocument()
})

test('historical version of the default bundle is not marked as current default', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      ...versionResponse('published'),
      id: 'version-1',
      is_default: true,
      current_published_version_id: 'version-2',
    }),
  )

  await renderAt(RiskRuleVersionEditorPage, '/risk-rule-bundle-versions/version-1', [
    { path: '/risk-rule-bundle-versions/:versionId', component: RiskRuleVersionEditorPage },
  ])

  await waitFor(() => expect(screen.getByText('查看已发布规则 v1')).toBeInTheDocument())
  expect(screen.queryByText('当前默认规则版本')).not.toBeInTheDocument()
})

test('first draft blocks creation until its condition is complete', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      id: 'bundle-1',
      organization_id: 'org-1',
      name: '空规则集',
      status: 'active',
      current_published_version_id: null,
      is_default: false,
      version: 1,
      versions: [],
    }),
  )

  await renderAt(RiskRuleBundleDetailPage, '/risk-rule-bundles/bundle-1', [
    { path: '/risk-rule-bundles/:bundleId', component: RiskRuleBundleDetailPage },
  ])
  await waitFor(() => expect(screen.getByText('空规则集')).toBeInTheDocument())
  await fireEvent.click(screen.getByRole('button', { name: '新建草稿' }))
  await fireEvent.update(screen.getByLabelText('变更说明'), '建立第一版')
  await fireEvent.update(screen.getByLabelText('首条规则键'), 'first_rule')
  await fireEvent.update(screen.getByLabelText('首条风险类型'), 'payment_terms')
  await fireEvent.update(screen.getByLabelText('首条风险建议'), '请复核付款条件。')
  await fireEvent.click(screen.getByRole('button', { name: '创建草稿' }))

  await waitFor(() =>
    expect(
      screen.getByText('第 1 条规则：关键词条件需要选择合同全文并填写关键词。'),
    ).toBeInTheDocument(),
  )
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('publishing a draft saves the complete local draft before publishing', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(versionResponse('draft', 1)))
    .mockResolvedValueOnce(response(versionResponse('draft', 2)))
    .mockResolvedValueOnce(response(versionResponse('published', 3)))

  await renderAt(RiskRuleVersionEditorPage, '/risk-rule-bundle-versions/version-1', [
    { path: '/risk-rule-bundle-versions/:versionId', component: RiskRuleVersionEditorPage },
  ])
  await waitFor(() => expect(screen.getByText('编辑规则草稿 v1')).toBeInTheDocument())
  await fireEvent.update(screen.getByLabelText('变更说明'), '发布前保存的说明')
  await fireEvent.click(screen.getByRole('button', { name: '发布版本' }))
  await fireEvent.click(await screen.findByRole('button', { name: '发布' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('PATCH')
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({
    change_note: '发布前保存的说明',
    version: 1,
  })
  expect(fetchMock.mock.calls[2]?.[1]?.method).toBe('POST')
  expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({})
  await waitFor(() => expect(screen.getByText('查看已发布规则 v1')).toBeInTheDocument())
})

test('draft version conflict keeps local edits on screen', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(versionResponse('draft', 1)))
    .mockResolvedValueOnce(
      response(
        {
          error: {
            code: 'RESOURCE_VERSION_CONFLICT',
            message: '资源已被更新，请刷新后重试。',
            request_id: 'req-conflict',
          },
        },
        409,
      ),
    )

  await renderAt(RiskRuleVersionEditorPage, '/risk-rule-bundle-versions/version-1', [
    { path: '/risk-rule-bundle-versions/:versionId', component: RiskRuleVersionEditorPage },
  ])
  await waitFor(() => expect(screen.getByText('编辑规则草稿 v1')).toBeInTheDocument())
  const note = screen.getByLabelText('变更说明')
  await fireEvent.update(note, '保留这段本地说明')
  await fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))

  await waitFor(() => expect(screen.getByText(/当前本地修改仍保留/)).toBeInTheDocument())
  expect(note).toHaveValue('保留这段本地说明')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('reviewer sees published bundle detail without write controls', async () => {
  sessionState.current = sessionWithRole('reviewer')
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      id: 'bundle-1',
      organization_id: 'org-1',
      name: '只读规则集',
      status: 'active',
      current_published_version_id: 'version-1',
      is_default: true,
      version: 2,
      versions: [],
    }),
  )

  await renderAt(RiskRuleBundleDetailPage, '/risk-rule-bundles/bundle-1', [
    { path: '/risk-rule-bundles/:bundleId', component: RiskRuleBundleDetailPage },
  ])
  await waitFor(() => expect(screen.getByText('只读规则集')).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: '编辑规则集' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '新建草稿' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '停用规则集' })).not.toBeInTheDocument()
})

test('resource page uses the resource organization role for write controls', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [
      adminSession.memberships[0]!,
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'reviewer',
        status: 'active',
      },
    ],
  }
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-1')).toBe(true)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      id: 'bundle-2',
      organization_id: 'org-2',
      name: '第二组织规则集',
      status: 'active',
      current_published_version_id: 'version-2',
      is_default: true,
      version: 2,
      versions: [],
    }),
  )

  await renderAt(RiskRuleBundleDetailPage, '/risk-rule-bundles/bundle-2', [
    { path: '/risk-rule-bundles/:bundleId', component: RiskRuleBundleDetailPage },
  ])

  await waitFor(() => expect(screen.getByText('第二组织规则集')).toBeInTheDocument())
  expect(currentOrganizationId.value).toBe('org-2')
  expect(screen.queryByRole('button', { name: '编辑规则集' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '新建草稿' })).not.toBeInTheDocument()
})

test('version deep link synchronizes the application organization context', async () => {
  sessionState.current = {
    ...adminSession,
    memberships: [
      adminSession.memberships[0]!,
      {
        organization_id: 'org-2',
        organization_name: '第二组织',
        role: 'reviewer',
        status: 'active',
      },
    ],
  }
  sessionState.loaded = true
  expect(selectCurrentOrganization('org-1')).toBe(true)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      ...versionResponse('published'),
      organization_id: 'org-2',
      bundle_id: 'bundle-2',
      id: 'version-2',
      is_default: true,
      current_published_version_id: 'version-2',
    }),
  )

  await renderAt(RiskRuleVersionEditorPage, '/risk-rule-bundle-versions/version-2', [
    { path: '/risk-rule-bundle-versions/:versionId', component: RiskRuleVersionEditorPage },
  ])

  await waitFor(() => expect(screen.getByText('查看已发布规则 v1')).toBeInTheDocument())
  expect(currentOrganizationId.value).toBe('org-2')
})

test('viewer receives an explicit forbidden state', async () => {
  sessionState.current = sessionWithRole('viewer')
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response(
      {
        error: {
          code: 'FORBIDDEN',
          message: '当前账户没有权限执行此操作。',
          request_id: 'req-viewer',
        },
      },
      403,
    ),
  )

  await renderAt(RiskRuleBundleListPage, '/risk-rule-bundles', [
    { path: '/risk-rule-bundles', component: RiskRuleBundleListPage },
  ])
  await waitFor(() => expect(screen.getByText('无法访问风险规则')).toBeInTheDocument())
  expect(screen.getByText('当前账户没有权限执行此操作。')).toBeInTheDocument()
})
