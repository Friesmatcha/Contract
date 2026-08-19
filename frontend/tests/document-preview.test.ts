import { cleanup, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, test, vi } from 'vitest'

import DocumentPreviewPage from '@/pages/documents/DocumentPreviewPage.vue'
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
    routes: [{ path: '/documents/:documentVersionId', component: DocumentPreviewPage }],
  })
  await router.push(path)
  await router.isReady()
  return render(DocumentPreviewPage, { global: { plugins: [router, ElementPlus] } })
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
  csrf_token: 'csrf-documents',
}

test('DOCX preview falls back from physical pages to ordered logical blocks', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(
      response(
        { error: { code: 'DOCUMENT_NOT_FOUND', message: '文档不存在。', request_id: 'req-page' } },
        404,
      ),
    )
    .mockResolvedValueOnce(
      response({
        document_version_id: 'doc-1',
        document_kind: 'docx',
        page_count: 0,
        blocks: [
          {
            id: 'block-1',
            order_no: 1,
            block_type: 'heading',
            page_no: null,
            paragraph_no: 1,
            table_path: null,
            text: '采购协议',
            bbox: null,
            source_spans: [
              {
                document_version_id: 'doc-1',
                kind: 'docx_paragraph',
                page_no: null,
                paragraph_no: 1,
                table_path: null,
                start_offset: 0,
                end_offset: 4,
                bbox: null,
                quote: '采购协议',
              },
            ],
          },
        ],
      }),
    )

  await renderAt('/documents/doc-1')

  await waitFor(() => expect(screen.getAllByText('采购协议').length).toBeGreaterThan(0))
  expect(screen.getAllByText('段落 1').length).toBeGreaterThan(0)
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(fetchMock.mock.calls[1]?.[0]).toBe(
    '/api/v1/documents/doc-1/blocks?include_source_spans=true',
  )
  expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('X-Organization-ID')).toBe('org-1')
})

test('PDF preview shows the physical page and OCR quality warning', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response({
      document_version_id: 'doc-2',
      document_kind: 'pdf',
      page_no: 2,
      page_count: 4,
      width: 600,
      height: 800,
      text: '页面文本',
      image_file_id: 'image-2',
      ocr_status: 'low_confidence',
      ocr_confidence: 0.65,
      error_code: 'OCR_LOW_CONFIDENCE',
      error_message: '页面 OCR 置信度较低，请人工复核。',
      blocks: [
        {
          id: 'block-2',
          order_no: 1,
          block_type: 'paragraph',
          page_no: 2,
          paragraph_no: null,
          table_path: null,
          text: '页面文本',
          bbox: null,
          source_spans: [],
        },
      ],
    }),
  )

  await renderAt('/documents/doc-2?page=2')

  await waitFor(() => expect(screen.getAllByText('页面文本').length).toBeGreaterThan(0))
  expect(screen.getByText('低置信度')).toBeInTheDocument()
  expect(screen.getByAltText('合同页面预览')).toHaveAttribute(
    'src',
    '/api/v1/files/image-2/download?disposition=inline',
  )
  expect(screen.getByRole('spinbutton')).toHaveValue(2)
})

test('preview exposes a safe retry state while parsing is not ready', async () => {
  sessionState.current = currentSession
  sessionState.loaded = true
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    response(
      {
        error: {
          code: 'DOCUMENT_NOT_READY',
          message: '文档仍在解析或解析失败，请稍后重试。',
          request_id: 'req-processing',
        },
      },
      409,
    ),
  )

  await renderAt('/documents/doc-3')

  await waitFor(() => expect(screen.getByText('文档预览加载失败')).toBeInTheDocument())
  expect(screen.getByText('文档仍在解析或解析失败，请稍后重试。')).toBeInTheDocument()
  expect(screen.getByText('请求 ID：req-processing')).toBeInTheDocument()
})
