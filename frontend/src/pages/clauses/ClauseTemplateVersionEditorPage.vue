<script setup lang="ts">
import { ArrowLeft, Delete, Edit, Plus, Promotion, Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getClauseTemplateVersion, publishClauseTemplateVersion, updateClauseTemplateVersion } from '@/api/clauseTemplates'
import type { ClauseSeverity, ClauseTemplateVersion, StandardClause, StandardClauseInput } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { activeOrganizationMemberships, selectCurrentOrganization } from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const versionId = computed(() => String(route.params.versionId ?? ''))
const templateId = computed(() => String(route.params.templateId ?? ''))
const version = ref<ClauseTemplateVersion | null>(null)
const clauses = ref<StandardClauseInput[]>([])
const changeNote = ref('')
const loading = ref(true)
const saving = ref(false)
const publishing = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const conflictMessage = ref('')
const editorOpen = ref(false)
const editingIndex = ref<number | null>(null)
const clauseDraft = ref<StandardClauseInput>(blankClause())
const savedFingerprint = ref('')
let loadGeneration = 0

const resourceMembership = computed(() => activeOrganizationMemberships.value.find(
  (membership) => membership.organization_id === version.value?.organization_id,
))
const canManage = computed(() => resourceMembership.value?.role === 'org_admin')
const readOnly = computed(() => version.value?.status === 'published' || !canManage.value)
const organizationContextMissing = computed(() => activeOrganizationMemberships.value.length === 0)
const dirty = computed(() => savedFingerprint.value !== fingerprint())

function blankClause(): StandardClauseInput {
  return {
    clause_key: '', name: '', standard_text: '', allowed_deviation: '', severity: 'medium',
    applicability: {}, suggestion: '', enabled: true, order_no: 1,
  }
}

function inputClause(clause: StandardClause): StandardClauseInput {
  const input = { ...clause }
  Reflect.deleteProperty(input, 'id')
  return input
}

function fingerprint(): string {
  return JSON.stringify({ changeNote: changeNote.value, clauses: clauses.value })
}

function formatDate(value: string | null): string {
  if (!value) return '未发布'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function severityLabel(value: ClauseSeverity): string {
  return value === 'high' ? '高' : value === 'medium' ? '中' : '低'
}

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(): Promise<void> {
  const generation = ++loadGeneration
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  conflictMessage.value = ''
  try {
    const loaded = await getClauseTemplateVersion(versionId.value)
    if (generation !== loadGeneration) return
    version.value = loaded
    clauses.value = loaded.clauses.map(inputClause)
    changeNote.value = loaded.change_note
    savedFingerprint.value = fingerprint()
    selectCurrentOrganization(loaded.organization_id)
  } catch (error) {
    if (generation === loadGeneration) setPageError(error)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function openNewClause(): void {
  editingIndex.value = null
  clauseDraft.value = { ...blankClause(), order_no: clauses.value.length + 1 }
  editorOpen.value = true
}

function openClause(index: number): void {
  editingIndex.value = index
  clauseDraft.value = JSON.parse(JSON.stringify(clauses.value[index])) as StandardClauseInput
  editorOpen.value = true
}

function validateClause(): string | null {
  if (!clauseDraft.value.clause_key.trim() || !clauseDraft.value.name.trim() || !clauseDraft.value.standard_text.trim() || !clauseDraft.value.suggestion.trim()) return '请填写条款编号、名称、标准文本和建议文本。'
  const duplicateKey = clauses.value.some((clause, index) => clause.clause_key === clauseDraft.value.clause_key.trim() && index !== editingIndex.value)
  if (duplicateKey) return '条款编号不能重复。'
  const duplicateOrder = clauses.value.some((clause, index) => clause.order_no === clauseDraft.value.order_no && index !== editingIndex.value)
  if (duplicateOrder) return '条款顺序不能重复。'
  return null
}

function saveClause(): void {
  const validationError = validateClause()
  if (validationError) { errorMessage.value = validationError; return }
  const normalized = { ...clauseDraft.value, clause_key: clauseDraft.value.clause_key.trim(), name: clauseDraft.value.name.trim(), standard_text: clauseDraft.value.standard_text.trim(), suggestion: clauseDraft.value.suggestion.trim() }
  if (editingIndex.value === null) clauses.value.push(normalized)
  else clauses.value[editingIndex.value] = normalized
  editorOpen.value = false
  errorMessage.value = ''
}

async function removeClause(index: number): Promise<void> {
  try { await ElMessageBox.confirm('删除后需要保存草稿才会提交。确定删除这条条款吗？', '确认删除条款', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch { return }
  clauses.value.splice(index, 1)
}

async function saveDraft(): Promise<boolean> {
  if (!version.value || readOnly.value || saving.value) return false
  saving.value = true
  errorMessage.value = ''
  conflictMessage.value = ''
  try {
    const saved = await updateClauseTemplateVersion(version.value.id, {
      clauses: clauses.value,
      change_note: changeNote.value.trim(),
      version: version.value.version,
    })
    version.value = saved
    clauses.value = saved.clauses.map(inputClause)
    changeNote.value = saved.change_note
    savedFingerprint.value = fingerprint()
    return true
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) conflictMessage.value = '服务器版本已变化，请重新加载后再保存。'
    setPageError(error)
    return false
  } finally { saving.value = false }
}

async function publish(): Promise<void> {
  if (!version.value || readOnly.value || publishing.value) return
  if (dirty.value && !(await saveDraft())) return
  try { await ElMessageBox.confirm('发布后所有条款正文不可编辑。确定发布此版本吗？', '确认发布版本', { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' }) } catch { return }
  publishing.value = true
  errorMessage.value = ''
  try {
    version.value = await publishClauseTemplateVersion(version.value.id)
    clauses.value = version.value.clauses.map(inputClause)
    changeNote.value = version.value.change_note
    savedFingerprint.value = fingerprint()
  } catch (error) { setPageError(error) } finally { publishing.value = false }
}

function discardChanges(): void {
  if (!version.value) return
  clauses.value = version.value.clauses.map(inputClause)
  changeNote.value = version.value.change_note
}

function goBack(): void { void router.push(`/clause-templates/${templateId.value}`) }

function beforeUnload(event: BeforeUnloadEvent): void {
  if (!dirty.value || readOnly.value) return
  event.preventDefault(); event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!dirty.value || readOnly.value) return true
  try { await ElMessageBox.confirm('离开后未保存修改将丢失。确定离开吗？', '未保存修改', { type: 'warning', confirmButtonText: '离开', cancelButtonText: '留下' }); return true } catch { return false }
})

onMounted(() => { void load(); window.addEventListener('beforeunload', beforeUnload) })
watch(versionId, () => { version.value = null; void load() })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <section class="admin-page clause-template-editor-page">
    <button
      class="back-link"
      type="button"
      @click="goBack"
    >
      <ElIcon><ArrowLeft /></ElIcon>返回模板详情
    </button>
    <ElResult
      v-if="organizationContextMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问模板版本"
      :description="errorMessage || '草稿仅对组织管理员开放，或版本不存在。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!version && (errorMessage || !loading)"
      title="模板版本加载失败"
      :description="errorMessage || '模板版本不存在。'"
      :request-id="errorRequestId"
      @retry="load"
    />
    <ElSkeleton
      v-else-if="loading"
      :rows="8"
      animated
      class="table-skeleton"
    />
    <template v-else-if="version">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            条款版本 · {{ version.id }}
          </div><h1>{{ readOnly ? '查看已发布条款' : '编辑条款草稿' }} v{{ version.version_no }}</h1><p>资源版本 v{{ version.version }} · {{ formatDate(version.effective_at) }}</p>
        </div>
        <div class="page-heading-actions">
          <ElTag :type="version.status === 'published' ? 'success' : 'warning'">
            {{ version.status === 'published' ? '已发布' : '草稿' }}
          </ElTag><ElTag
            v-if="version.is_default && version.id === version.current_published_version_id"
            type="success"
          >
            当前默认版本
          </ElTag>
        </div>
      </div>
      <ElAlert
        v-if="conflictMessage"
        :title="conflictMessage"
        type="warning"
        :closable="false"
        show-icon
        class="editor-alert"
      >
        <ElButton
          link
          type="warning"
          @click="load"
        >
          加载服务器版本
        </ElButton>
      </ElAlert>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
        class="editor-alert"
      >
        <p
          v-if="errorRequestId"
          class="request-id"
        >
          请求 ID：{{ errorRequestId }}
        </p>
      </ElAlert>
      <section class="form-panel clause-editor-note">
        <div class="section-heading">
          <div><h2>变更说明</h2><p>已发布版本只读；草稿保存后才能发布。</p></div><span class="technical-value">{{ clauses.length }} 条条款</span>
        </div><ElInput
          v-model="changeNote"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          :readonly="readOnly"
          aria-label="变更说明"
        />
      </section>
      <section class="table-panel clause-editor-table">
        <div class="section-heading rule-history-heading">
          <div><h2>标准条款（{{ clauses.length }}）</h2><p>{{ readOnly ? '已发布版本只读。' : '编辑条款后保存草稿。' }}</p></div><ElButton
            v-if="!readOnly"
            type="primary"
            :icon="Plus"
            @click="openNewClause"
          >
            新增条款
          </ElButton>
        </div><ElEmpty
          v-if="clauses.length === 0"
          description="当前版本暂无条款"
        /><ElTable
          v-else
          :data="clauses"
          row-key="clause_key"
          aria-label="标准条款编辑列表"
        >
          <ElTableColumn
            label="顺序"
            width="80"
            prop="order_no"
          /><ElTableColumn
            label="条款编号"
            min-width="160"
          >
            <template #default="scope">
              <span class="technical-value">{{ scope.row.clause_key }}</span>
            </template>
          </ElTableColumn><ElTableColumn
            label="条款名称"
            min-width="160"
            prop="name"
          /><ElTableColumn
            label="标准文本"
            min-width="320"
            show-overflow-tooltip
            prop="standard_text"
          /><ElTableColumn
            label="等级"
            width="90"
          >
            <template #default="scope">
              <ElTag :type="scope.row.severity === 'high' ? 'danger' : scope.row.severity === 'medium' ? 'warning' : 'info'">
                {{ severityLabel(scope.row.severity) }}
              </ElTag>
            </template>
          </ElTableColumn><ElTableColumn
            label="状态"
            width="90"
          >
            <template #default="scope">
              <ElSwitch
                v-model="scope.row.enabled"
                :disabled="readOnly"
                aria-label="启用条款"
              />
            </template>
          </ElTableColumn><ElTableColumn
            label="操作"
            width="150"
            align="right"
          >
            <template #default="scope">
              <ElButton
                v-if="!readOnly"
                link
                type="primary"
                :icon="Edit"
                @click="openClause(scope.$index)"
              >
                编辑
              </ElButton><ElButton
                v-if="!readOnly"
                link
                type="danger"
                :icon="Delete"
                @click="removeClause(scope.$index)"
              >
                删除
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </section>
      <div
        v-if="!readOnly"
        class="editor-actions"
      >
        <ElButton
          :icon="Refresh"
          :disabled="saving || publishing"
          @click="discardChanges"
        >
          放弃修改
        </ElButton><ElButton
          type="primary"
          :loading="saving"
          :disabled="publishing"
          @click="saveDraft"
        >
          保存草稿
        </ElButton><ElButton
          type="success"
          :icon="Promotion"
          :loading="publishing"
          :disabled="saving || clauses.length === 0"
          @click="publish"
        >
          发布版本
        </ElButton>
      </div>
    </template>
    <ElDrawer
      v-model="editorOpen"
      :title="editingIndex === null ? '新增标准条款' : '编辑标准条款'"
      direction="rtl"
      size="min(560px, 100vw)"
    >
      <ElForm label-position="top">
        <ElFormItem
          label="条款编号"
          required
        >
          <ElInput
            v-model="clauseDraft.clause_key"
            maxlength="128"
            aria-label="条款编号"
          />
        </ElFormItem><ElFormItem
          label="条款名称"
          required
        >
          <ElInput
            v-model="clauseDraft.name"
            maxlength="255"
            aria-label="条款名称"
          />
        </ElFormItem><ElFormItem
          label="标准文本"
          required
        >
          <ElInput
            v-model="clauseDraft.standard_text"
            type="textarea"
            :rows="5"
            maxlength="10000"
            aria-label="标准文本"
          />
        </ElFormItem><ElFormItem label="允许偏差">
          <ElInput
            v-model="clauseDraft.allowed_deviation"
            type="textarea"
            :rows="3"
            maxlength="2000"
            aria-label="允许偏差"
          />
        </ElFormItem><div class="form-row">
          <ElFormItem
            label="风险等级"
            required
          >
            <ElSelect
              v-model="clauseDraft.severity"
              aria-label="风险等级"
            >
              <ElOption
                label="高"
                value="high"
              /><ElOption
                label="中"
                value="medium"
              /><ElOption
                label="低"
                value="low"
              />
            </ElSelect>
          </ElFormItem><ElFormItem
            label="顺序"
            required
          >
            <ElInput
              v-model.number="clauseDraft.order_no"
              type="number"
              min="1"
              max="1000"
              aria-label="条款顺序"
            />
          </ElFormItem>
        </div><ElFormItem
          label="建议文本"
          required
        >
          <ElInput
            v-model="clauseDraft.suggestion"
            type="textarea"
            :rows="4"
            maxlength="2000"
            aria-label="建议文本"
          />
        </ElFormItem><ElFormItem label="启用">
          <ElSwitch
            v-model="clauseDraft.enabled"
            aria-label="启用条款"
          />
        </ElFormItem>
      </ElForm><template #footer>
        <ElButton @click="editorOpen = false">
          取消
        </ElButton><ElButton
          type="primary"
          @click="saveClause"
        >
          保存条款
        </ElButton>
      </template>
    </ElDrawer>
  </section>
</template>
