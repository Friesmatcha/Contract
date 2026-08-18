import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import PlatformModelConfigurationPage from '@/pages/platform/PlatformModelConfigurationPage.vue'
import PlatformOrganizationsPage from '@/pages/platform/PlatformOrganizationsPage.vue'
import OrganizationSettingsPage from '@/pages/organization/OrganizationSettingsPage.vue'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function renderAt(component: object, path: string, routes: Array<{ path: string; component: object }>) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return { router, ...render(component, { global: { plugins: [router, ElementPlus] } }) }
}

const organization = {
  id: 'org-1',
  name: '示例企业',
  status: 'active',
  retention_days: 180,
  settings: {
    file_size_limit_bytes: 20971520,
    page_limit: 100,
    concurrent_review_limit: 3,
    warn_on_medium_risk: false,
    ocr_low_confidence_threshold: 0.8,
    retention_days: 180,
    report_watermark: '仅供内部审核',
  },
  version: 1,
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

test('platform organization page renders list and submits the create contract', async () => {
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response({ items: [], next_cursor: null, has_more: false }))
    .mockResolvedValueOnce(response(organization, 201))

  const { router } = await renderAt(PlatformOrganizationsPage, '/platform/organizations', [
    { path: '/platform/organizations', component: PlatformOrganizationsPage },
    { path: '/platform/organizations/:organizationId', component: PlatformOrganizationsPage },
  ])

  await waitFor(() => expect(screen.getByText('暂无组织')).toBeInTheDocument())
  await fireEvent.click(screen.getAllByRole('button', { name: '新建组织' })[0] as HTMLElement)
  await fireEvent.update(screen.getByLabelText('组织名称', { exact: true }), '示例企业')
  await fireEvent.update(screen.getByRole('textbox', { name: '初始管理员邮箱' }), 'admin@example.com')
  await fireEvent.click(screen.getByRole('button', { name: '创建组织' }))

  await waitFor(() => expect(router.currentRoute.value.path).toBe('/platform/organizations/org-1'))
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/platform/organizations')
})

test('model configuration shows environment secret state without exposing an input', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      provider: 'qwen',
      model: 'qwen-test-model',
      model_source: 'environment',
      timeout_seconds: 60,
      max_retries: 3,
      hard_budget_enabled: false,
      usage_tracking_enabled: true,
      organization_overrides_allowed: false,
      secret_configured: false,
      status: 'active',
      version: 1,
    }),
  )

  await renderAt(PlatformModelConfigurationPage, '/platform/model-configuration', [
    { path: '/platform/model-configuration', component: PlatformModelConfigurationPage },
  ])

  await waitFor(() => expect(screen.getByText('模型环境未配置完成')).toBeInTheDocument())
  expect(screen.getByText('qwen-test-model')).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: /密钥|API Key/i })).not.toBeInTheDocument()
})

test('organization settings sends only the changed field and current version', async () => {
  const settings = { ...organization.settings, version: 1 }
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(
      response({
        id: 'org-1',
        name: '示例企业',
        status: 'active',
        my_role: 'org_admin',
        permissions: ['organization:read'],
      }),
    )
    .mockResolvedValueOnce(response(settings))
    .mockResolvedValueOnce(response({ ...settings, warn_on_medium_risk: true, version: 2 }))

  await renderAt(OrganizationSettingsPage, '/organizations/org-1/settings', [
    { path: '/organizations/:organizationId/settings', component: OrganizationSettingsPage },
  ])

  await waitFor(() => expect(screen.getByText('文件与并发')).toBeInTheDocument())
  const warningSwitch = document.querySelector('.el-switch')
  if (!(warningSwitch instanceof HTMLElement)) throw new Error('warning switch not rendered')
  await fireEvent.click(warningSwitch)
  await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

  expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
    warn_on_medium_risk: true,
    version: 1,
  })
})
