import { expect, test, type Page } from '@playwright/test'

const fileSummary = {
  id: 'file-1',
  version_no: 1,
  is_current: true,
  original_name: '采购合同.pdf',
  media_type: 'application/pdf',
  size_bytes: 24,
  scan_status: 'clean',
  storage_status: 'stored',
  created_at: '2026-08-19T06:00:00Z',
}

const organizationSession = {
  user: {
    id: 'admin-1',
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
  csrf_token: 'csrf-files',
}

const viewerSession = {
  user: {
    id: 'viewer-1',
    email: 'viewer@example.com',
    display_name: '业务查看者',
    status: 'active',
    is_platform_admin: false,
  },
  memberships: [
    {
      organization_id: 'org-1',
      organization_name: '示例企业',
      role: 'viewer',
      status: 'active',
    },
  ],
  csrf_token: 'csrf-viewer-files',
}

function contractWithFiles(files: typeof fileSummary[] = []) {
  return {
    id: 'contract-1',
    display_no: 'CTR-20260819-000001',
    title: '供应商采购合同',
    declared_type: 'purchase',
    status: 'active',
    owner_id: 'admin-1',
    current_file: files.find((file) => file.is_current) ?? null,
    files,
    latest_review: null,
    created_at: '2026-08-19T06:00:00Z',
    updated_at: '2026-08-19T06:00:00Z',
    version: 1,
  }
}

async function mockSession(page: Page, session: typeof organizationSession): Promise<void> {
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 200, json: session }),
  )
}

test('writer confirms the model notice and uploads a file version', async ({ page }, testInfo) => {
  let contract = contractWithFiles()
  await mockSession(page, organizationSession)
  await page.route('**/api/v1/contracts/contract-1', (route) =>
    route.fulfill({ status: 200, json: contract }),
  )
  await page.route('**/api/v1/contracts/contract-1/files', async (route) => {
    contract = contractWithFiles([fileSummary])
    await route.fulfill({
      status: 201,
      json: {
        file: fileSummary,
        contract_file_id: 'contract-file-1',
        version_no: 1,
        is_current: true,
        external_model_notice_acknowledged_at: '2026-08-19T06:00:00Z',
      },
    })
  })

  await page.goto('/contracts/contract-1/files')
  await expect(page.getByRole('heading', { name: '供应商采购合同' })).toBeVisible()
  await expect(page.getByText(/千问商用 API/)).toBeVisible()
  await expect(page.getByRole('button', { name: '上传文件' })).toBeDisabled()

  await page.locator('input[type="file"]').setInputFiles({
    name: '采购合同.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.7\n1 0 obj\n%%EOF'),
  })
  await page.getByRole('checkbox', { name: '我已阅读并确认合同内容将按系统说明用于自动审核' }).check()
  await expect(page.getByRole('button', { name: '上传文件' })).toBeEnabled()
  await page.getByRole('button', { name: '上传文件' }).click()

  await expect(page.getByText('采购合同.pdf')).toBeVisible()
  await expect(page.getByText('扫描完成')).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath(`contract-files-upload-${testInfo.project.name}.png`),
    fullPage: true,
  })
})

test('viewer sees file versions and the authorized download action without upload controls', async ({ page }, testInfo) => {
  await mockSession(page, viewerSession)
  await page.route('**/api/v1/contracts/contract-1', (route) =>
    route.fulfill({ status: 200, json: contractWithFiles([fileSummary]) }),
  )

  await page.goto('/contracts/contract-1/files')
  await expect(page.getByText('采购合同.pdf')).toBeVisible()
  await expect(page.getByRole('button', { name: '上传文件' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '下载文件' })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath(`contract-files-viewer-${testInfo.project.name}.png`),
    fullPage: true,
  })
})
