import { expect, test } from '@playwright/test'

const session = {
  user: {
    id: 'reviewer-1',
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
  csrf_token: 'csrf-document-preview',
}

test('contract preview renders a physical PDF page and evidence context', async ({ page }, testInfo) => {
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 200, json: session }),
  )
  await page.route('**/api/v1/documents/doc-1/pages/1*', (route) =>
    route.fulfill({
      status: 200,
      json: {
        document_version_id: 'doc-1',
        document_kind: 'pdf',
        page_no: 1,
        page_count: 3,
        width: 600,
        height: 800,
        text: '采购方应按约定支付合同价款。',
        image_file_id: null,
        ocr_status: 'not_required',
        ocr_confidence: null,
        error_code: null,
        error_message: null,
        blocks: [
          {
            id: 'block-1',
            order_no: 1,
            block_type: 'paragraph',
            page_no: 1,
            paragraph_no: null,
            table_path: null,
            text: '采购方应按约定支付合同价款。',
            bbox: null,
            source_spans: [
              {
                document_version_id: 'doc-1',
                kind: 'pdf_page',
                page_no: 1,
                paragraph_no: null,
                table_path: null,
                start_offset: 0,
                end_offset: 15,
                bbox: null,
                quote: '采购方应按约定支付合同价款。',
              },
            ],
          },
        ],
      },
    }),
  )

  await page.goto('/documents/doc-1')
  await expect(page.getByText('采购方应按约定支付合同价款。').first()).toBeVisible()
  await expect(page.getByRole('spinbutton', { name: '页码' })).toHaveValue('1')
  await expect(page.getByText('第 1 页').last()).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath(`document-preview-${testInfo.project.name}.png`),
    fullPage: true,
  })
})
