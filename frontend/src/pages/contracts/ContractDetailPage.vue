<script setup lang="ts">
import { Download, Edit, FolderRemove, Key, RefreshLeft, Upload } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  archiveContract,
  getContract,
  grantContractAccess,
  revokeContractAccess,
  updateContract,
  restoreContract,
} from '@/api/contracts'
import { listOrganizationMembers } from '@/api/organizations'
import type { Contract, ContractType, Membership } from '@/api/types'
import PageState from '@/components/PageState.vue'
import {
  currentOrganizationId,
  currentOrganizationMembership,
} from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const contractId = computed(() => String(route.params.contractId ?? ''))
const organizationId = currentOrganizationId
const role = computed(() => currentOrganizationMembership.value?.role)
const canWrite = computed(() => role.value === 'org_admin' || role.value === 'reviewer')
const isAdmin = computed(() => role.value === 'org_admin')

const contract = ref<Contract | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string>()
const editing = ref(false)
const editSubmitting = ref(false)
const editTitle = ref('')
const editType = ref<ContractType | ''>('')
const members = ref<Membership[]>([])
const selectedViewer = ref('')
const grantSubmitting = ref(false)

function typeLabel(value: ContractType | null): string {
  if (!value) return '未声明'
  return {
    purchase: '采购',
    sales: '销售',
    nda: '保密协议',
    outsourcing: '服务外包',
    employment: '劳动',
    other: '其他/待确认',
  }[value]
}

function statusLabel(value: Contract['status']): string {
  return value === 'active' ? '活跃' : '已归档'
}

function formatDate(value: string | null): string {
  if (!value) return '未归档'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function openFiles(): void {
  void router.push(`/contracts/${contractId.value}/files`)
}

function openFile(fileId: string): void {
  window.open(`/api/v1/files/${encodeURIComponent(fileId)}/download`, '_blank', 'noopener,noreferrer')
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
    editTitle.value = contract.value.title
    editType.value = contract.value.declared_type || ''
  } catch (error) {
    setError('page', error)
  } finally {
    loading.value = false
  }
}

async function loadViewerMembers(): Promise<void> {
  if (!isAdmin.value || members.value.length > 0) return
  try {
    const page = await listOrganizationMembers(organizationId.value, {
      role: 'viewer',
      status: 'active',
      limit: 100,
    })
    members.value = page.items
  } catch (error) {
    setError('action', error)
  }
}

function startEdit(): void {
  if (!contract.value) return
  editTitle.value = contract.value.title
  editType.value = contract.value.declared_type || ''
  actionError.value = ''
  editing.value = true
}

async function saveEdit(): Promise<void> {
  if (!contract.value || editSubmitting.value || !editTitle.value.trim()) return
  editSubmitting.value = true
  actionError.value = ''
  try {
    contract.value = await updateContract(contract.value.id, {
      title: editTitle.value.trim(),
      declared_type: editType.value || null,
      version: contract.value.version,
    })
    editing.value = false
  } catch (error) {
    setError('action', error)
    if (error instanceof ApiError && error.code === 'RESOURCE_VERSION_CONFLICT') await load()
  } finally {
    editSubmitting.value = false
  }
}

async function archive(): Promise<void> {
  if (!contract.value || contract.value.status !== 'active') return
  try {
    await ElMessageBox.confirm(
      '归档后合同元数据将只读，仍可由组织管理员恢复。确定归档吗？',
      '确认归档合同',
      { type: 'warning', confirmButtonText: '归档', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  actionError.value = ''
  try {
    await archiveContract(contract.value.id)
    await load()
  } catch (error) {
    setError('action', error)
  }
}

async function restore(): Promise<void> {
  if (!contract.value || contract.value.status !== 'archived') return
  try {
    await ElMessageBox.confirm('恢复后合同可继续编辑。确定恢复吗？', '确认恢复合同', {
      confirmButtonText: '恢复',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  actionError.value = ''
  try {
    await restoreContract(contract.value.id)
    await load()
  } catch (error) {
    setError('action', error)
  }
}

async function grantAccess(): Promise<void> {
  if (!contract.value || !selectedViewer.value || grantSubmitting.value) return
  grantSubmitting.value = true
  actionError.value = ''
  try {
    await grantContractAccess(contract.value.id, selectedViewer.value)
    selectedViewer.value = ''
  } catch (error) {
    setError('action', error)
  } finally {
    grantSubmitting.value = false
  }
}

async function revokeAccess(): Promise<void> {
  if (!contract.value || !selectedViewer.value || grantSubmitting.value) return
  try {
    await ElMessageBox.confirm('撤销后该查看者将无法再看到此合同。确定撤销吗？', '确认撤销授权', {
      type: 'warning',
      confirmButtonText: '撤销授权',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  grantSubmitting.value = true
  actionError.value = ''
  try {
    await revokeContractAccess(contract.value.id, selectedViewer.value)
    selectedViewer.value = ''
  } catch (error) {
    setError('action', error)
  } finally {
    grantSubmitting.value = false
  }
}

onMounted(() => {
  void load()
  void loadViewerMembers()
})
</script>

<template>
  <section class="admin-page contract-detail-page">
    <button
      class="back-link"
      type="button"
      @click="router.push('/contracts')"
    >
      返回合同目录
    </button>
    <PageState
      v-if="forbidden"
      title="无法访问合同"
      :description="errorMessage || '合同不存在或当前账户没有查看权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!contract && (errorMessage || !loading)"
      title="合同详情加载失败"
      :description="errorMessage || '合同不存在。'"
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
          <p>合同元数据与后续审核资产入口。</p>
        </div>
        <div class="page-heading-actions">
          <ElTag
            :type="contract.status === 'active' ? 'success' : 'info'"
            effect="light"
          >
            {{ statusLabel(contract.status) }}
          </ElTag>
          <ElButton
            v-if="canWrite && contract.status === 'active'"
            :icon="Edit"
            @click="startEdit"
          >
            编辑元数据
          </ElButton>
          <ElButton
            v-if="canWrite && contract.status === 'active'"
            type="warning"
            :icon="FolderRemove"
            @click="archive"
          >
            归档
          </ElButton>
          <ElButton
            v-if="isAdmin && contract.status === 'archived'"
            type="primary"
            :icon="RefreshLeft"
            @click="restore"
          >
            恢复
          </ElButton>
        </div>
      </div>

      <ElAlert
        v-if="actionError"
        :title="actionError"
        :description="actionRequestId ? `请求 ID：${actionRequestId}` : undefined"
        type="error"
        :closable="false"
        show-icon
      />

      <div class="detail-grid contract-detail-grid">
        <section class="summary-panel">
          <div class="section-heading">
            <div>
              <h2>基本信息</h2>
              <p>当前合同元数据。</p>
            </div>
          </div>
          <dl class="metadata-list metadata-list-single">
            <div>
              <dt>合同编号</dt><dd class="technical-value">
                {{ contract.display_no }}
              </dd>
            </div>
            <div><dt>声明类型</dt><dd>{{ typeLabel(contract.declared_type) }}</dd></div>
            <div>
              <dt>负责人 ID</dt><dd class="technical-value">
                {{ contract.owner_id }}
              </dd>
            </div>
            <div><dt>创建时间</dt><dd>{{ formatDate(contract.created_at) }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatDate(contract.updated_at) }}</dd></div>
          </dl>
        </section>

        <section class="summary-panel">
          <div class="section-heading">
            <div>
              <h2>文件版本</h2>
              <p>安全文件版本与授权下载。</p>
            </div>
            <ElButton
              v-if="canWrite && contract.status === 'active'"
              :icon="Upload"
              @click="openFiles"
            >
              上传文件
            </ElButton>
          </div>
          <ElEmpty
            v-if="contract.files.length === 0"
            description="暂无合同文件"
          >
            <ElButton
              v-if="canWrite && contract.status === 'active'"
              :icon="Upload"
              @click="openFiles"
            >
              上传文件
            </ElButton>
          </ElEmpty>
          <ElTable
            v-else
            :data="contract.files"
            row-key="id"
          >
            <ElTableColumn
              prop="version_no"
              label="版本"
            />
            <ElTableColumn
              prop="original_name"
              label="文件名"
              show-overflow-tooltip
            />
            <ElTableColumn label="扫描状态">
              <template #default="scope">
                <ElTag
                  v-if="scope.row.scan_status === 'clean'"
                  type="success"
                >
                  扫描完成
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="状态">
              <template #default="scope">
                <ElTag
                  v-if="scope.row.is_current"
                  type="success"
                >
                  当前版本
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作">
              <template #default="scope">
                <ElButton
                  text
                  :icon="Download"
                  aria-label="下载文件"
                  title="下载文件"
                  @click="openFile(scope.row.id)"
                />
              </template>
            </ElTableColumn>
          </ElTable>
        </section>

        <section class="summary-panel">
          <div class="section-heading">
            <div>
              <h2>最近审核</h2>
              <p>审核任务将在后续 Phase 建立。</p>
            </div>
          </div>
          <ElEmpty
            v-if="!contract.latest_review"
            description="暂无审核任务"
          />
          <ElDescriptions
            v-else
            :column="1"
            border
          >
            <ElDescriptionsItem label="任务 ID">
              {{ contract.latest_review.id }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="状态">
              {{ contract.latest_review.status }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </section>

        <section
          v-if="isAdmin"
          class="summary-panel"
        >
          <div class="section-heading">
            <div>
              <h2>Viewer 查看授权</h2>
              <p>契约当前没有授权列表读取接口；选择同组织有效 viewer 执行授予或撤销。</p>
            </div>
            <ElIcon><Key /></ElIcon>
          </div>
          <ElSelect
            v-model="selectedViewer"
            clearable
            placeholder="选择有效 viewer"
            aria-label="选择 viewer"
          >
            <ElOption
              v-for="member in members"
              :key="member.user_id || member.id"
              :label="member.display_name || member.email"
              :value="member.user_id || member.id"
            />
          </ElSelect>
          <div class="page-heading-actions access-actions">
            <ElButton
              :loading="grantSubmitting"
              :disabled="!selectedViewer"
              @click="grantAccess"
            >
              授予查看权限
            </ElButton>
            <ElButton
              type="danger"
              :icon="FolderRemove"
              :loading="grantSubmitting"
              :disabled="!selectedViewer"
              @click="revokeAccess"
            >
              撤销查看权限
            </ElButton>
          </div>
        </section>
      </div>
    </template>

    <ElDialog
      v-model="editing"
      title="编辑合同元数据"
      width="480px"
      destroy-on-close
    >
      <ElForm
        label-position="top"
        class="admin-form"
      >
        <ElFormItem
          label="合同名称"
          required
        >
          <ElInput
            v-model="editTitle"
            maxlength="500"
            aria-label="编辑合同名称"
          />
        </ElFormItem>
        <ElFormItem label="声明合同类型">
          <ElSelect
            v-model="editType"
            clearable
            aria-label="编辑合同类型"
          >
            <ElOption
              label="采购"
              value="purchase"
            />
            <ElOption
              label="销售"
              value="sales"
            />
            <ElOption
              label="保密协议"
              value="nda"
            />
            <ElOption
              label="服务外包"
              value="outsourcing"
            />
            <ElOption
              label="劳动"
              value="employment"
            />
            <ElOption
              label="其他/待确认"
              value="other"
            />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="editing = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="editSubmitting"
          @click="saveEdit"
        >
          保存修改
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
