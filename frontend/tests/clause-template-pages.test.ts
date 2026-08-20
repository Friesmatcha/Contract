import { cleanup, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import type { AuthSession } from '@/api/types'
import ClauseTemplateDetailPage from '@/pages/clauses/ClauseTemplateDetailPage.vue'
import ClauseTemplateListPage from '@/pages/clauses/ClauseTemplateListPage.vue'
import ClauseTemplateVersionEditorPage from '@/pages/clauses/ClauseTemplateVersionEditorPage.vue'
import { sessionState } from '@/features/auth/session'

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
  memberships: [{
    organization_id: 'org-1',
    organization_name: '示例企业',
    role: 'org_admin',
    status: 'active',
  }],
  csrf_token: 'csrf-clause',
}

async function renderAt(component: object, path: string, routes: Array<{ path: string; component: object }>) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return render(component, { global: { plugins: [router, ElementPlus] } })
}

const clause = {
  id: 'clause-1',
  clause_key: 'payment',
  name: '付款',
  standard_text: '验收后 30 日内付款。',
  allowed_deviation: '期限可协商。',
  severity: 'medium' as const,
  applicability: {},
  suggestion: '明确付款期限。',
  enabled: true,
  order_no: 1,
}

test('clause template list renders default marker and tenant-scoped request', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
    items: [{
      organization_id: 'org-1',
      id: 'template-1',
      name: '采购合同基线',
      contract_type: 'purchase',
      business_scenario: 'standard',
      status: 'active',
      current_published_version_id: 'version-1',
      is_default: true,
      version: 1,
    }],
    next_cursor: null,
    has_more: false,
  }))

  await renderAt(ClauseTemplateListPage, '/clause-templates', [
    { path: '/clause-templates', component: ClauseTemplateListPage },
  ])

  await waitFor(() => expect(screen.getByText('采购合同基线')).toBeInTheDocument())
  expect(screen.getByText('默认')).toBeInTheDocument()
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('clause template detail renders version history and default action', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
    organization_id: 'org-1',
    id: 'template-1',
    name: '采购合同备选基线',
    contract_type: 'purchase',
    business_scenario: 'standard',
    status: 'active',
    current_published_version_id: 'version-1',
    is_default: false,
    version: 1,
    versions: [{
      organization_id: 'org-1',
      id: 'version-1',
      version_no: 1,
      status: 'published',
      change_note: '初始化条款',
      effective_at: '2026-08-19T06:00:00Z',
      published_by: 'user-1',
      clauses: [clause],
    }],
  }))

  await renderAt(ClauseTemplateDetailPage, '/clause-templates/template-1', [
    { path: '/clause-templates/:templateId', component: ClauseTemplateDetailPage },
  ])

  await waitFor(() => expect(screen.getByText('采购合同备选基线')).toBeInTheDocument())
  expect(screen.getByText('版本历史（1）')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '设为默认' })).toBeInTheDocument()
})

test('published clause version is read-only while draft exposes save action', async () => {
  sessionState.current = adminSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
    organization_id: 'org-1',
    id: 'version-1',
    template_id: 'template-1',
    version_no: 1,
    status: 'published',
    change_note: '初始化条款',
    effective_at: '2026-08-19T06:00:00Z',
    published_by: 'user-1',
    version: 1,
    is_default: true,
    current_published_version_id: 'version-1',
    clauses: [clause],
  }))

  await renderAt(ClauseTemplateVersionEditorPage, '/clause-templates/template-1/versions/version-1', [
    { path: '/clause-templates/:templateId/versions/:versionId', component: ClauseTemplateVersionEditorPage },
  ])

  await waitFor(() => expect(screen.getByText('查看已发布条款 v1')).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: '保存草稿' })).not.toBeInTheDocument()
  expect(screen.getByText('已发布')).toBeInTheDocument()
})
