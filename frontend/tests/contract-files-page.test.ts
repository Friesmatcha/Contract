import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import ContractFilesPage from '@/pages/contracts/ContractFilesPage.vue'
import type { AuthSession } from '@/api/types'
import { sessionState } from '@/features/auth/session'

afterEach(() => {
  cleanup()
  sessionState.current = null
  sessionState.loaded = false
  vi.restoreAllMocks()
})

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function renderAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/contracts/:contractId/files', component: ContractFilesPage }],
  })
  await router.push(path)
  await router.isReady()
  return render(ContractFilesPage, { global: { plugins: [router, ElementPlus] } })
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
  csrf_token: 'csrf-files',
}

const contract = {
  id: 'contract-1',
  display_no: 'CTR-20260819-000001',
  title: '供应商采购合同',
  declared_type: 'purchase',
  status: 'active',
  owner_id: 'user-1',
  current_file: {
    id: 'file-1',
    version_no: 1,
    is_current: true,
    original_name: '采购合同.pdf',
    media_type: 'application/pdf',
    size_bytes: 2048,
    scan_status: 'clean',
    storage_status: 'stored',
    created_at: '2026-08-19T06:00:00Z',
  },
  files: [
    {
      id: 'file-1',
      version_no: 1,
      is_current: true,
      original_name: '采购合同.pdf',
      media_type: 'application/pdf',
      size_bytes: 2048,
      scan_status: 'clean',
      storage_status: 'stored',
      created_at: '2026-08-19T06:00:00Z',
    },
  ],
  latest_review: null,
  created_at: '2026-08-19T06:00:00Z',
  updated_at: '2026-08-19T06:00:00Z',
  version: 1,
}

test('file versions page shows upload controls, server file metadata, and download action', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(contract))
  const openMock = vi.spyOn(window, 'open').mockImplementation(() => null)

  await renderAt('/contracts/contract-1/files')

  await waitFor(() => expect(screen.getByText('采购合同.pdf')).toBeInTheDocument())
  expect(screen.getByText('外部模型告知')).toBeInTheDocument()
  expect(screen.getByText(/千问商用 API/)).toBeInTheDocument()
  expect(screen.getByText(/请勿上传未获授权的数据/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '上传文件' })).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: '下载文件' }))
  expect(openMock).toHaveBeenCalledWith(
    '/api/v1/files/file-1/download?disposition=attachment',
    '_blank',
    'noopener,noreferrer',
  )
  expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('file versions page keeps a skeleton while the initial contract request is pending', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise<Response>(() => {}))

  await renderAt('/contracts/contract-1/files')

  await waitFor(() => expect(screen.getByText(/正在加载服务端文件版本/)).toBeInTheDocument())
  expect(screen.queryByText('暂无合同文件')).not.toBeInTheDocument()
})

test('file picker rejects a mismatched extension and MIME before upload', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...contract, files: [] }))

  await renderAt('/contracts/contract-1/files')
  await waitFor(() => expect(screen.getByText('暂无合同文件')).toBeInTheDocument())
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['not-a-pdf'], 'contract.exe', { type: 'application/pdf' })
  await fireEvent.change(input, { target: { files: [file] } })

  expect(screen.getByText('请选择扩展名和文件类型匹配的 DOCX、PDF、PNG 或 JPEG 文件。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '上传文件' })).toBeDisabled()
})
