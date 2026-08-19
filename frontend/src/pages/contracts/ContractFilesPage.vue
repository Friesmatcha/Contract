<script setup lang="ts">
import { Close, Download, UploadFilled } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  contractFileDownloadUrl,
  getContract,
  uploadContractFile,
} from '@/api/contracts'
import type { Contract, ContractFileSummary } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { sessionState } from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const contractId = computed(() => String(route.params.contractId ?? ''))
const organizationId = computed(() =>
  sessionState.current?.memberships.find((membership) => membership.status === 'active')
    ?.organization_id ?? '',
)
const role = computed(() =>
  sessionState.current?.memberships.find(
    (membership) => membership.organization_id === organizationId.value,
  )?.role,
)
const canWrite = computed(() =>
  (role.value === 'org_admin' || role.value === 'reviewer') && contract.value?.status === 'active',
)

const contract = ref<Contract | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string>()
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const makeCurrent = ref(true)
const noticeAcknowledged = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)

const mediaTypes: Record<string, string> = {
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
}

function setError(target: 'page' | 'action', error: unknown): void {
  const safe = toSafeDisplayError(error)
  if (target === 'page') {
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } else {
    actionError.value = safe.message
    actionRequestId.value = safe.requestId
  }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  forbidden.value = false
  try {
    contract.value = await getContract(contractId.value, organizationId.value)
  } catch (error) {
    setError('page', error)
  } finally {
    loading.value = false
  }
}

function chooseFile(file: File | undefined): void {
  if (!file || uploading.value) return
  const suffix = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
  const expectedType = mediaTypes[suffix]
  if (!expectedType || file.type !== expectedType) {
    actionError.value = '请选择扩展名和文件类型匹配的 DOCX、PDF、PNG 或 JPEG 文件。'
    selectedFile.value = null
    return
  }
  actionError.value = ''
  selectedFile.value = file
}

function chooseFromInput(event: Event): void {
  chooseFile((event.target as HTMLInputElement).files?.[0])
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  chooseFile(event.dataTransfer?.files[0])
}

function formatBytes(size: number | null | undefined): string {
  if (size === null || size === undefined) return '未知'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function mediaTypeLabel(value: string | null | undefined): string {
  if (!value) return '未知'
  if (value.includes('pdf')) return 'PDF'
  if (value.includes('word')) return 'DOCX'
  if (value.includes('png')) return 'PNG'
  return 'JPEG'
}

function scanLabel(value: ContractFileSummary['scan_status']): string {
  return value === 'clean' ? '扫描完成' : value === 'failed' ? '扫描失败' : '待扫描'
}

function openDownload(fileId: string): void {
  window.open(contractFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer')
}

function clearSelection(): void {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function upload(): Promise<void> {
  if (!contract.value || !selectedFile.value || !canWrite.value || !noticeAcknowledged.value) return
  uploading.value = true
  uploadProgress.value = 0
  actionError.value = ''
  actionRequestId.value = undefined
  try {
    await uploadContractFile(
      contract.value.id,
      selectedFile.value,
      makeCurrent.value,
      crypto.randomUUID(),
      (percent) => {
        uploadProgress.value = percent
      },
    )
    await load()
    ElMessage.success('文件上传并完成安全扫描。')
    clearSelection()
  } catch (error) {
    setError('action', error)
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="admin-page contract-files-page">
    <button
      class="back-link"
      type="button"
      @click="router.push(`/contracts/${contractId}`)"
    >
      返回合同详情
    </button>

    <PageState
      v-if="forbidden"
      title="无法访问合同文件"
      :description="errorMessage || '合同不存在或当前账户没有查看权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <section
      v-else-if="loading && !contract"
      class="table-panel file-history-panel contract-files-loading"
    >
      <div class="section-heading file-history-heading">
        <div>
          <h2>版本历史</h2>
          <p>正在加载服务端文件版本。</p>
        </div>
      </div>
      <div class="table-skeleton">
        <ElSkeleton
          :rows="6"
          animated
        />
      </div>
    </section>
    <PageState
      v-else-if="!contract"
      title="文件版本加载失败"
      :description="errorMessage || '合同文件暂时无法加载。'"
      :request-id="errorRequestId"
      @retry="load"
    />
    <template v-else-if="contract">
      <div class="page-heading">
        <div>
          <div class="technical-value contract-display-no">
            {{ contract.display_no }}
          </div>
          <h1>{{ contract.title }}</h1>
          <p>文件版本、告知确认和安全下载入口。</p>
        </div>
        <ElTag :type="contract.status === 'active' ? 'success' : 'info'">
          {{ contract.status === 'active' ? '活跃' : '已归档' }}
        </ElTag>
      </div>

      <ElAlert
        class="external-model-notice"
        title="外部模型告知"
        type="warning"
        :closable="false"
        show-icon
      >
        您确认已获得处理该合同的合法授权。合同内容将发送至千问商用 API，用于合同分类、要素抽取、风险分析和条款比对；系统将记录调用范围与模型版本。请勿上传未获授权的数据。
      </ElAlert>

      <ElAlert
        v-if="actionError"
        :title="actionError"
        :description="actionRequestId ? `请求 ID：${actionRequestId}` : undefined"
        type="error"
        :closable="false"
        show-icon
      />

      <div class="contract-files-layout">
        <section
          v-if="role === 'org_admin' || role === 'reviewer'"
          class="form-panel upload-panel"
        >
          <div class="section-heading">
            <div>
              <h2>上传新版本</h2>
              <p>服务端会重新校验文件类型、签名、大小并完成病毒扫描。</p>
            </div>
          </div>
          <ElAlert
            v-if="contract.status === 'archived'"
            title="归档合同不可上传文件"
            type="info"
            :closable="false"
            show-icon
          />
          <button
            class="file-drop-zone"
            type="button"
            :disabled="!canWrite || uploading"
            @click="fileInput?.click()"
            @drop="onDrop"
            @dragover.prevent
          >
            <UploadFilled class="file-drop-icon" />
            <strong>点击或拖拽文件到此处</strong>
            <span>支持 DOCX、PDF、PNG、JPG、JPEG 格式</span>
          </button>
          <input
            ref="fileInput"
            class="visually-hidden"
            type="file"
            accept=".docx,.pdf,.png,.jpg,.jpeg"
            :disabled="!canWrite || uploading"
            @change="chooseFromInput"
          >
          <div
            v-if="selectedFile"
            class="selected-file"
          >
            <div>
              <strong>{{ selectedFile.name }}</strong>
              <span>{{ formatBytes(selectedFile.size) }}</span>
            </div>
            <ElButton
              text
              :icon="Close"
              aria-label="移除已选文件"
              :disabled="uploading"
              @click="clearSelection"
            />
          </div>
          <div class="upload-options">
            <ElCheckbox
              v-model="makeCurrent"
              :disabled="!canWrite || uploading"
            >
              设为当前版本
            </ElCheckbox>
            <ElCheckbox
              v-model="noticeAcknowledged"
              :disabled="!canWrite || uploading"
            >
              我已阅读并确认合同内容将按系统说明用于自动审核
            </ElCheckbox>
          </div>
          <ElButton
            type="primary"
            :loading="uploading"
            :disabled="!selectedFile || !noticeAcknowledged || !canWrite"
            @click="upload"
          >
            上传文件
          </ElButton>
        </section>

        <section class="files-history-column">
          <section
            v-if="uploading"
            class="summary-panel upload-progress-panel"
          >
            <div class="section-heading">
              <h2>正在上传到浏览器</h2>
              <span class="technical-value">{{ uploadProgress }}%</span>
            </div>
            <ElProgress
              :percentage="uploadProgress"
              :show-text="false"
              :stroke-width="8"
            />
            <p class="muted-text">
              进度仅表示浏览器上传字节，扫描结果将在服务器响应后显示。
            </p>
          </section>

          <section class="table-panel file-history-panel">
            <div class="section-heading file-history-heading">
              <div>
                <h2>版本历史</h2>
                <p>仅显示服务端已返回的文件版本信息。</p>
              </div>
            </div>
            <ElTable
              v-if="contract.files.length > 0"
              :data="contract.files"
              row-key="id"
              table-layout="fixed"
            >
              <ElTableColumn
                label="版本"
                width="80"
              >
                <template #default="scope">
                  v{{ scope.row.version_no }}
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="文件名"
                min-width="220"
                show-overflow-tooltip
              >
                <template #default="scope">
                  {{ scope.row.original_name || '未返回' }}
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="类型"
                width="90"
              >
                <template #default="scope">
                  {{ mediaTypeLabel(scope.row.media_type) }}
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="大小"
                width="110"
                align="right"
              >
                <template #default="scope">
                  {{ formatBytes(scope.row.size_bytes) }}
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="扫描状态"
                width="120"
              >
                <template #default="scope">
                  <ElTag :type="scope.row.scan_status === 'clean' ? 'success' : 'warning'">
                    {{ scanLabel(scope.row.scan_status) }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="当前版本"
                width="110"
                align="center"
              >
                <template #default="scope">
                  <ElTag
                    v-if="scope.row.is_current"
                    type="primary"
                  >
                    当前
                  </ElTag>
                  <span
                    v-else
                    class="muted-text"
                  >-</span>
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="上传时间"
                width="170"
              >
                <template #default="scope">
                  {{ formatDate(scope.row.created_at) }}
                </template>
              </ElTableColumn>
              <ElTableColumn
                label="操作"
                width="90"
                align="center"
              >
                <template #default="scope">
                  <ElButton
                    text
                    :icon="Download"
                    aria-label="下载文件"
                    title="下载文件"
                    @click="openDownload(scope.row.id)"
                  />
                </template>
              </ElTableColumn>
            </ElTable>
            <ElEmpty
              v-else
              description="暂无合同文件"
            >
              <span class="muted-text">
                {{ canWrite ? '选择合法文件并完成告知确认后上传。' : '当前账户只能查看授权的文件版本。' }}
              </span>
            </ElEmpty>
          </section>
        </section>
      </div>
    </template>
  </section>
</template>
