import { apiErrorFromResponse, apiFetch, isApiErrorCode, type ApiError } from '@/api/client'
import { getCsrfToken } from '@/features/auth/csrf'
import type {
  Contract,
  ContractAccessGrant,
  ContractFileUploadResponse,
  ContractListQuery,
  ContractStatusResponse,
  CreateContractRequest,
  CursorPage,
  UpdateContractRequest,
} from '@/api/types'

const API_BASE = '/api/v1'

export type ContractApiErrorCode =
  | 'AUTHENTICATION_REQUIRED'
  | 'CONTRACT_ARCHIVED'
  | 'CONTRACT_NOT_ARCHIVED'
  | 'CONTRACT_NOT_FOUND'
  | 'CROSS_ORGANIZATION_ACCESS'
  | 'FORBIDDEN'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'ORGANIZATION_CONTEXT_REQUIRED'
  | 'ORGANIZATION_NOT_FOUND'
  | 'ORG_ADMIN_REQUIRED'
  | 'RESOURCE_VERSION_CONFLICT'
  | 'VALIDATION_ERROR'

function contractPath(contractId: string): string {
  return `${API_BASE}/contracts/${encodeURIComponent(contractId)}`
}

function appendQuery(path: string, query: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query) as Array<[string, unknown]>) {
    if (value !== undefined) params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `${path}?${serialized}` : path
}

function organizationHeaders(organizationId: string): HeadersInit {
  return { 'X-Organization-ID': organizationId }
}

export function isContractApiError<Code extends ContractApiErrorCode>(
  error: unknown,
  code: Code,
): error is ApiError & { readonly code: Code } {
  return isApiErrorCode(error, code)
}

export function listContracts(
  organizationId: string,
  query: ContractListQuery = {},
): Promise<CursorPage<Contract>> {
  return apiFetch(appendQuery(`${API_BASE}/contracts`, query), {
    headers: organizationHeaders(organizationId),
  })
}

export function createContract(
  organizationId: string,
  body: CreateContractRequest,
  idempotencyKey: string,
): Promise<Contract> {
  return apiFetch(`${API_BASE}/contracts`, {
    method: 'POST',
    headers: { ...organizationHeaders(organizationId), 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getContract(contractId: string, organizationId: string): Promise<Contract> {
  return apiFetch(contractPath(contractId), { headers: organizationHeaders(organizationId) })
}

export function updateContract(contractId: string, body: UpdateContractRequest): Promise<Contract> {
  return apiFetch(contractPath(contractId), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function archiveContract(contractId: string): Promise<ContractStatusResponse> {
  return apiFetch(`${contractPath(contractId)}/archive`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function restoreContract(contractId: string): Promise<ContractStatusResponse> {
  return apiFetch(`${contractPath(contractId)}/restore`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function grantContractAccess(
  contractId: string,
  userId: string,
): Promise<ContractAccessGrant> {
  return apiFetch(`${contractPath(contractId)}/access-grants/${encodeURIComponent(userId)}`, {
    method: 'PUT',
    body: JSON.stringify({ access_level: 'read' }),
  })
}

export function revokeContractAccess(contractId: string, userId: string): Promise<void> {
  return apiFetch(`${contractPath(contractId)}/access-grants/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  })
}

export function uploadContractFile(
  contractId: string,
  file: File,
  makeCurrent: boolean,
  idempotencyKey: string,
  onProgress: (percent: number) => void,
): Promise<ContractFileUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('make_current', String(makeCurrent))
  form.append('external_model_notice_acknowledged', 'true')

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', `${API_BASE}/contracts/${encodeURIComponent(contractId)}/files`)
    request.withCredentials = true
    request.setRequestHeader('Idempotency-Key', idempotencyKey)
    const csrfToken = getCsrfToken()
    if (csrfToken) request.setRequestHeader('X-CSRF-Token', csrfToken)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () => reject(new Error('上传请求无法连接。'))
    request.onload = () => {
      const requestId = request.getResponseHeader('X-Request-ID') || undefined
      let body: unknown
      try {
        body = JSON.parse(request.responseText)
      } catch {
        reject(new Error('服务返回了无法识别的响应。'))
        return
      }
      if (request.status < 200 || request.status >= 300) {
        reject(apiErrorFromResponse(request.status, body, requestId))
        return
      }
      onProgress(100)
      resolve(body as ContractFileUploadResponse)
    }
    request.send(form)
  })
}

export function contractFileDownloadUrl(
  fileId: string,
  disposition: 'attachment' | 'inline' = 'attachment',
): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}/download?disposition=${disposition}`
}
