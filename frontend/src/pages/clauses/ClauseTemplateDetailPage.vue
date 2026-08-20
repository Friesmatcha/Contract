<script setup lang="ts">
import { ArrowLeft, Edit, Plus, Promotion, Switch, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createClauseTemplateVersion,
  getClauseTemplate,
  updateClauseTemplate,
} from '@/api/clauseTemplates'
import type {
  ClauseContractType,
  ClauseTemplateDetail,
  ClauseTemplateStatus,
  ClauseTemplateVersionSummary,
  StandardClauseInput,
} from '@/api/types'
import PageState from '@/components/PageState.vue'
import { activeOrganizationMemberships, selectCurrentOrganization } from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const templateId = computed(() => String(route.params.templateId ?? ''))
const template = ref<ClauseTemplateDetail | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string>()
const action = ref<'default' | 'disable' | 'enable' | 'metadata' | null>(null)
const draftOpen = ref(false)
const draftNote = ref('')
const creatingDraft = ref(false)
const metadataOpen = ref(false)
const editName = ref('')
const editScenario = ref('')
let loadGeneration = 0

const resourceMembership = computed(() =>
  activeOrganizationMemberships.value.find(
    (membership) => membership.organization_id === template.value?.organization_id,
  ),
)
const canManage = computed(() => resourceMembership.value?.role === 'org_admin')
const currentPublishedVersion = computed(() =>
  template.value?.versions.find((version) => version.id === template.value?.current_published_version_id),
)
const contractTypes: Record<ClauseContractType, string> = {
  purchase: '采购合同',
  sales: '销售合同',
  nda: '保密协议',
  outsourcing: '外包合同',
  employment: '劳动合同',
}

function statusLabel(value: ClauseTemplateStatus): string {
  return value === 'active' ? '启用' : '已停用'
}

function versionStatusLabel(value: ClauseTemplateVersionSummary['status']): string {
  return value === 'published' ? '已发布' : '草稿'
}

function formatDate(value: string | null): string {
  if (!value) return '未发布'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

function setActionError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  actionError.value = safe.message
  actionRequestId.value = safe.requestId
}

async function load(): Promise<void> {
  const generation = ++loadGeneration
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  try {
    const loaded = await getClauseTemplate(templateId.value, true)
    if (generation !== loadGeneration) return
    template.value = loaded
    selectCurrentOrganization(loaded.organization_id)
  } catch (error) {
    if (generation === loadGeneration) setPageError(error)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function clauseInputs(version: ClauseTemplateVersionSummary | undefined): StandardClauseInput[] {
  return (version?.clauses ?? []).map((clause) => {
    const input = { ...clause }
    Reflect.deleteProperty(input, 'id')
    return input
  })
}

function openDraft(): void {
  draftNote.value = ''
  actionError.value = ''
  draftOpen.value = true
}

async function createDraft(): Promise<void> {
  if (!template.value || !draftNote.value.trim() || creatingDraft.value) return
  creatingDraft.value = true
  actionError.value = ''
  try {
    const version = await createClauseTemplateVersion(
      template.value.id,
      {
        change_note: draftNote.value.trim(),
        source_version_id: currentPublishedVersion.value?.id,
        clauses: clauseInputs(currentPublishedVersion.value),
      },
      crypto.randomUUID(),
    )
    draftOpen.value = false
    await router.push(`/clause-templates/${template.value.id}/versions/${version.id}`)
  } catch (error) {
    setActionError(error)
  } finally {
    creatingDraft.value = false
  }
}

function openVersion(version: ClauseTemplateVersionSummary): void {
  void router.push(`/clause-templates/${templateId.value}/versions/${version.id}`)
}

function openMetadata(): void {
  if (!template.value) return
  editName.value = template.value.name
  editScenario.value = template.value.business_scenario
  actionError.value = ''
  metadataOpen.value = true
}

async function saveMetadata(): Promise<void> {
  if (!template.value || !editName.value.trim() || action.value) return
  action.value = 'metadata'
  actionError.value = ''
  try {
    await updateClauseTemplate(template.value.id, {
      name: editName.value.trim(),
      business_scenario: editScenario.value.trim() || 'standard',
      version: template.value.version,
    })
    metadataOpen.value = false
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) await load()
    setActionError(error)
  } finally {
    action.value = null
  }
}

async function switchDefault(): Promise<void> {
  if (!template.value || !canManage.value || template.value.is_default || action.value) return
  action.value = 'default'
  try {
    await ElMessageBox.confirm(
      '切换后同一合同类型和业务场景的新审核将使用此模板的当前发布版本。确定切换吗？',
      '确认切换默认模板',
      { type: 'warning', confirmButtonText: '切换', cancelButtonText: '取消' },
    )
    actionError.value = ''
    await updateClauseTemplate(template.value.id, { is_default: true, version: template.value.version })
    await load()
  } catch (error) {
    if (error instanceof Error && error.message === 'cancel') return
    if (error instanceof ApiError && error.status === 409) await load()
    if (error instanceof ApiError) setActionError(error)
  } finally {
    action.value = null
  }
}

async function updateStatus(nextStatus: ClauseTemplateStatus): Promise<void> {
  if (!template.value || !canManage.value || action.value) return
  action.value = nextStatus === 'disabled' ? 'disable' : 'enable'
  try {
    if (nextStatus === 'disabled') {
      await ElMessageBox.confirm('停用后不能创建或发布新版本。确定停用吗？', '确认停用模板', {
        type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消',
      })
    }
    actionError.value = ''
    await updateClauseTemplate(template.value.id, { status: nextStatus, version: template.value.version })
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) await load()
    if (error instanceof ApiError) setActionError(error)
  } finally {
    action.value = null
  }
}

onMounted(() => void load())
watch(templateId, () => { template.value = null; void load() })
</script>

<template>
  <section class="admin-page clause-template-detail-page">
    <button
      class="back-link"
      type="button"
      @click="router.push('/clause-templates')"
    >
      <ElIcon><ArrowLeft /></ElIcon>
      返回条款模板
    </button>
    <ElResult
      v-if="!template && !loading && !errorMessage"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问条款模板"
      :description="errorMessage || '模板不存在或当前账户没有访问权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!template && (errorMessage || !loading)"
      title="模板详情加载失败"
      :description="errorMessage || '模板不存在。'"
      :request-id="errorRequestId"
      @retry="load"
    />
    <ElSkeleton
      v-else-if="loading"
      :rows="8"
      animated
      class="table-skeleton"
    />
    <template v-else-if="template">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            条款模板 · {{ template.id }}
          </div>
          <h1>{{ template.name }}</h1>
          <p>{{ contractTypes[template.contract_type] }} · 场景 {{ template.business_scenario }} · 资源版本 v{{ template.version }}</p>
        </div>
        <div class="page-heading-actions">
          <ElTag :type="template.status === 'active' ? 'success' : 'info'">
            {{ statusLabel(template.status) }}
          </ElTag>
          <ElTag
            v-if="template.is_default"
            type="success"
          >
            当前默认
          </ElTag>
        </div>
      </div>

      <ElAlert
        v-if="actionError"
        :title="actionError"
        type="error"
        :closable="false"
        show-icon
        class="editor-alert"
      >
        <p
          v-if="actionRequestId"
          class="request-id"
        >
          请求 ID：{{ actionRequestId }}
        </p>
      </ElAlert>

      <section class="detail-grid clause-detail-grid">
        <div class="summary-panel">
          <div class="section-heading">
            <div><h2>模板信息</h2><p>默认模板只在合同类型和业务场景完全匹配时生效。</p></div>
            <ElButton
              v-if="canManage"
              link
              type="primary"
              :icon="Edit"
              @click="openMetadata"
            >
              编辑
            </ElButton>
          </div>
          <dl class="metadata-list metadata-list-single">
            <div><dt>合同类型</dt><dd>{{ contractTypes[template.contract_type] }}</dd></div>
            <div>
              <dt>业务场景</dt><dd class="technical-value">
                {{ template.business_scenario }}
              </dd>
            </div>
            <div><dt>当前发布版本</dt><dd>{{ currentPublishedVersion ? `v${currentPublishedVersion.version_no}` : '未发布' }}</dd></div>
            <div><dt>版本数量</dt><dd>{{ template.versions.length }}</dd></div>
          </dl>
        </div>
        <div class="summary-panel">
          <div class="section-heading">
            <div><h2>模板操作</h2><p>版本正文只能通过新建草稿修改。</p></div>
          </div>
          <div class="detail-actions">
            <ElButton
              v-if="canManage && template.status === 'active'"
              type="primary"
              :icon="Plus"
              @click="openDraft"
            >
              新建草稿版本
            </ElButton>
            <ElButton
              v-if="canManage && !template.is_default && template.status === 'active' && template.current_published_version_id"
              :icon="Switch"
              :loading="action === 'default'"
              @click="switchDefault"
            >
              设为默认
            </ElButton>
            <ElButton
              v-if="canManage && template.status === 'active'"
              type="warning"
              :icon="VideoPause"
              :loading="action === 'disable'"
              @click="updateStatus('disabled')"
            >
              停用模板
            </ElButton>
            <ElButton
              v-if="canManage && template.status === 'disabled'"
              type="success"
              :icon="VideoPlay"
              :loading="action === 'enable'"
              @click="updateStatus('active')"
            >
              重新启用
            </ElButton>
          </div>
          <p class="form-hint">
            发布后的版本不可编辑，历史审核引用保留原版本。
          </p>
        </div>
      </section>

      <section class="table-panel clause-version-history">
        <div class="section-heading rule-history-heading">
          <div><h2>版本历史（{{ template.versions.length }}）</h2><p>发布版本对审核员可见，草稿仅组织管理员可见。</p></div>
        </div>
        <ElEmpty
          v-if="template.versions.length === 0"
          description="暂无版本"
        />
        <ElTable
          v-else
          :data="template.versions"
          row-key="id"
          aria-label="条款模板版本历史"
          @row-click="openVersion"
        >
          <ElTableColumn
            label="版本"
            width="110"
          >
            <template #default="scope">
              <button
                class="table-link"
                type="button"
                @click.stop="openVersion(scope.row)"
              >
                v{{ scope.row.version_no }}
              </button>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="120"
          >
            <template #default="scope">
              <ElTag :type="scope.row.status === 'published' ? 'success' : 'warning'">
                {{ versionStatusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="变更说明"
            min-width="300"
            prop="change_note"
          />
          <ElTableColumn
            label="生效时间"
            min-width="190"
          >
            <template #default="scope">
              {{ formatDate(scope.row.effective_at) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="条款数量"
            width="120"
          >
            <template #default="scope">
              {{ scope.row.clauses?.length ?? 0 }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="140"
            align="right"
          >
            <template #default="scope">
              <ElButton
                link
                type="primary"
                :icon="scope.row.status === 'draft' ? Edit : Promotion"
                @click.stop="openVersion(scope.row)"
              >
                {{ scope.row.status === 'draft' ? '编辑草稿' : '查看版本' }}
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </section>
    </template>

    <ElDialog
      v-model="draftOpen"
      title="新建条款草稿版本"
      width="min(560px, calc(100vw - 32px))"
    >
      <p class="dialog-context">
        将从当前发布版本复制条款；没有发布版本时创建空草稿，可在编辑器中添加条款。
      </p>
      <ElForm label-position="top">
        <ElFormItem
          label="变更说明"
          required
        >
          <ElInput
            v-model="draftNote"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            aria-label="变更说明"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="draftOpen = false">
          取消
        </ElButton><ElButton
          type="primary"
          :loading="creatingDraft"
          :disabled="!draftNote.trim()"
          @click="createDraft"
        >
          创建草稿
        </ElButton>
      </template>
    </ElDialog>
    <ElDialog
      v-model="metadataOpen"
      title="编辑模板信息"
      width="min(560px, calc(100vw - 32px))"
    >
      <ElForm label-position="top">
        <ElFormItem
          label="模板名称"
          required
        >
          <ElInput
            v-model="editName"
            maxlength="255"
            aria-label="模板名称"
          />
        </ElFormItem><ElFormItem label="业务场景">
          <ElInput
            v-model="editScenario"
            maxlength="128"
            aria-label="业务场景"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="metadataOpen = false">
          取消
        </ElButton><ElButton
          type="primary"
          :loading="action === 'metadata'"
          :disabled="!editName.trim()"
          @click="saveMetadata"
        >
          保存
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
