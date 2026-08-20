<script setup lang="ts">
import { ArrowLeft, Delete, Edit, Plus, Promotion, Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  getRiskRuleVersion,
  publishRiskRuleVersion,
  updateRiskRuleVersion,
} from '@/api/riskRules'
import type {
  RiskRuleInput,
  RiskRuleCondition,
  RiskRuleSeverity,
  RiskRuleVersion,
} from '@/api/types'
import PageState from '@/components/PageState.vue'
import RiskRuleConditionEditor from '@/components/RiskRuleConditionEditor.vue'
import {
  activeOrganizationMemberships,
  selectCurrentOrganization,
} from '@/features/auth/session'
import {
  normalizeRiskRule,
  validateRiskRule,
  validateRiskRules,
} from '@/features/risk-rules/validation'

const route = useRoute()
const router = useRouter()
const versionId = computed(() => String(route.params.versionId ?? ''))
const resourceOrganizationId = computed(() => version.value?.organization_id ?? '')
const resourceMembership = computed(() =>
  activeOrganizationMemberships.value.find(
    (membership) => membership.organization_id === resourceOrganizationId.value,
  ),
)
const canManage = computed(() => resourceMembership.value?.role === 'org_admin')
const readOnly = computed(() => version.value?.status === 'published' || !canManage.value)

const version = ref<RiskRuleVersion | null>(null)
const rules = ref<RiskRuleInput[]>([])
const changeNote = ref('')
const resourceVersion = ref(1)
const loading = ref(true)
const saving = ref(false)
const publishing = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const conflictMessage = ref('')
const savedFingerprint = ref('')
const editorOpen = ref(false)
const editingIndex = ref<number | null>(null)
const ruleDraft = ref<RiskRuleInput>(newRule())
const organizationContextMissing = computed(
  () => activeOrganizationMemberships.value.length === 0,
)
let loadGeneration = 0

function newRule(): RiskRuleInput {
  return {
    rule_key: '',
    risk_type: '',
    engine: 'deterministic',
    condition: { operator: 'keyword', field: 'contract_text', value: '' },
    severity: 'medium',
    suggestion: '',
    enabled: true,
  }
}

function conditionSummary(condition: RiskRuleCondition): string {
  const operator = condition.operator
  if (operator === 'keyword') return `关键词：${condition.value}`
  if (operator === 'regex') return `正则：${condition.pattern}`
  if (operator === 'semantic') return '语义判断'
  if (operator === 'field_exists') return `字段存在：${condition.field}`
  if (operator === 'field_missing') return `字段缺失：${condition.field}`
  if (operator === 'amount_threshold' || operator === 'date_threshold') {
    return `${operator === 'amount_threshold' ? '金额' : '日期'}：${condition.field} ${condition.comparison} ${condition.value}`
  }
  if (operator === 'not') return `不满足：${conditionSummary(condition.condition)}`
  if (operator === 'all' || operator === 'any') {
    return `${operator === 'all' ? '全部满足' : '任一满足'}（${condition.conditions.length} 项）`
  }
  return '未知条件'
}

function cloneRule(rule: RiskRuleInput): RiskRuleInput {
  return JSON.parse(JSON.stringify(rule)) as RiskRuleInput
}

function currentFingerprint(): string {
  return JSON.stringify({
    change_note: changeNote.value.trim(),
    rules: payloadRules(),
  })
}

const dirty = computed(
  () => version.value?.status === 'draft' && savedFingerprint.value !== currentFingerprint(),
)

function statusLabel(value: RiskRuleVersion['status']): string {
  return value === 'published' ? '已发布' : '草稿'
}

function severityLabel(value: RiskRuleSeverity): string {
  return { high: '高', medium: '中', low: '低' }[value]
}

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(): Promise<void> {
  const generation = ++loadGeneration
  const requestedVersionId = versionId.value
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  if (!requestedVersionId) {
    version.value = null
    loading.value = false
    return
  }
  loading.value = true
  try {
    const loaded = await getRiskRuleVersion(requestedVersionId)
    if (
      generation !== loadGeneration ||
      requestedVersionId !== versionId.value
    ) {
      return
    }
    version.value = loaded
    selectCurrentOrganization(loaded.organization_id)
    rules.value = loaded.rules.map(cloneRule)
    changeNote.value = loaded.change_note
    resourceVersion.value = loaded.version
    savedFingerprint.value = currentFingerprint()
    conflictMessage.value = ''
  } catch (error) {
    if (generation !== loadGeneration) return
    setPageError(error)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function openNewRule(): void {
  if (readOnly.value) return
  editingIndex.value = null
  ruleDraft.value = newRule()
  editorOpen.value = true
}

function openExistingRule(index: number): void {
  if (readOnly.value) return
  const source = rules.value[index]
  if (!source) return
  editingIndex.value = index
  ruleDraft.value = cloneRule(source)
  editorOpen.value = true
}

function saveRule(): void {
  const candidate = normalizeRiskRule(ruleDraft.value)
  const ruleError = validateRiskRule(candidate)
  if (ruleError) {
    ElMessage.warning(ruleError)
    return
  }
  const nextRules = [...rules.value]
  if (editingIndex.value === null) nextRules.push(candidate)
  else nextRules[editingIndex.value] = candidate
  const rulesError = validateRiskRules(nextRules)
  if (rulesError) {
    ElMessage.warning(rulesError)
    return
  }
  rules.value = nextRules
  editorOpen.value = false
}

async function removeRule(index: number): Promise<void> {
  if (readOnly.value) return
  try {
    await ElMessageBox.confirm('删除只影响当前草稿，保存后才会写入服务器。确定删除这条规则吗？', '确认删除规则', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  rules.value.splice(index, 1)
}

function payloadRules(): RiskRuleInput[] {
  return rules.value.map(normalizeRiskRule)
}

async function saveDraft(force = false): Promise<boolean> {
  if (!version.value || readOnly.value || saving.value) return false
  if (!force && !dirty.value) return true
  if (!changeNote.value.trim()) {
    ElMessage.warning('草稿需要填写变更说明。')
    return false
  }
  const rulesError = validateRiskRules(rules.value)
  if (rulesError) {
    ElMessage.warning(rulesError)
    return false
  }
  saving.value = true
  conflictMessage.value = ''
  errorMessage.value = ''
  try {
    const updated = await updateRiskRuleVersion(version.value.id, {
      change_note: changeNote.value.trim(),
      rules: payloadRules(),
      version: resourceVersion.value,
    })
    version.value = updated
    rules.value = updated.rules
    changeNote.value = updated.change_note
    resourceVersion.value = updated.version
    savedFingerprint.value = currentFingerprint()
    return true
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    if (error instanceof ApiError && error.code === 'RESOURCE_VERSION_CONFLICT') {
      conflictMessage.value = '草稿已被其他人更新。当前本地修改仍保留，请选择重新加载服务器版本或继续编辑。'
    }
    return false
  } finally {
    saving.value = false
  }
}

async function publish(): Promise<void> {
  if (!version.value || readOnly.value || publishing.value) return
  try {
    await ElMessageBox.confirm(
      '发布后该版本不可编辑，已有审核任务仍会继续引用原版本。确定发布吗？',
      '确认发布规则版本',
      { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  publishing.value = true
  errorMessage.value = ''
  try {
    const saved = await saveDraft(true)
    if (!saved) return
    const published = await publishRiskRuleVersion(version.value.id)
    version.value = published
    rules.value = published.rules
    resourceVersion.value = published.version
    savedFingerprint.value = currentFingerprint()
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    if (error instanceof ApiError && error.status === 409) {
      conflictMessage.value = '发布冲突，服务器状态可能已变化；本地修改仍保留，请重新加载后确认。'
    }
  } finally {
    publishing.value = false
  }
}

async function discardChanges(): Promise<void> {
  if (!dirty.value) {
    await load()
    return
  }
  try {
    await ElMessageBox.confirm(
      '放弃后本地修改将被服务器版本覆盖。确定继续吗？',
      '放弃本地修改',
      { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑' },
    )
  } catch {
    return
  }
  await load()
}

async function reloadLatest(): Promise<void> {
  await load()
}

function goBack(): void {
  void router.push(`/risk-rule-bundles/${version.value?.bundle_id ?? ''}`)
}

function beforeUnload(event: BeforeUnloadEvent): void {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm(
      '离开后本地修改将丢失。确定离开吗？',
      '未保存修改',
      { type: 'warning', confirmButtonText: '离开', cancelButtonText: '留下' },
    )
    return true
  } catch {
    return false
  }
})

onMounted(() => {
  void load()
  window.addEventListener('beforeunload', beforeUnload)
})

watch(versionId, () => {
  version.value = null
  void load()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <section class="admin-page risk-rule-editor-page">
    <button
      class="back-link"
      type="button"
      @click="goBack"
    >
      <ElIcon><ArrowLeft /></ElIcon>
      返回规则集详情
    </button>

    <ElResult
      v-if="organizationContextMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问规则版本"
      :description="errorMessage || '草稿仅对组织管理员开放，或版本不存在。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!version && (errorMessage || !loading)"
      title="规则版本加载失败"
      :description="errorMessage || '规则版本不存在。'"
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
            规则版本 · {{ version.id }}
          </div>
          <h1>{{ version.status === 'draft' ? '编辑规则草稿' : '查看已发布规则' }} v{{ version.version_no }}</h1>
          <p>所属规则集 {{ version.bundle_id }} · 资源版本 v{{ version.version }}</p>
        </div>
        <div class="page-heading-actions">
          <ElTag :type="version.status === 'published' ? 'success' : 'warning'">
            {{ statusLabel(version.status) }}
          </ElTag>
          <ElTag
            v-if="version.is_default && version.id === version.current_published_version_id"
            type="success"
          >
            当前默认规则版本
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
          @click="reloadLatest"
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
      <ElAlert
        v-if="dirty"
        title="有未保存修改"
        type="info"
        :closable="false"
        show-icon
        class="editor-alert"
      />

      <section class="form-panel rule-editor-note">
        <div class="section-heading">
          <div>
            <h2>变更说明</h2>
            <p>规则条件由服务端白名单 Schema 校验，不执行任意代码、SQL 或脚本。</p>
          </div>
          <span class="technical-value">资源版本 v{{ resourceVersion }}</span>
        </div>
        <ElInput
          v-model="changeNote"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          :readonly="readOnly"
          placeholder="说明本次规则更新的目的和范围"
          aria-label="变更说明"
        />
      </section>

      <section class="table-panel rule-editor-table">
        <div class="section-heading rule-history-heading">
          <div>
            <h2>规则列表（{{ rules.length }}）</h2>
            <p>{{ readOnly ? '已发布版本只读。' : '保存草稿后才会提交本地修改。' }}</p>
          </div>
          <ElButton
            v-if="!readOnly"
            type="primary"
            :icon="Plus"
            @click="openNewRule"
          >
            新增规则
          </ElButton>
        </div>
        <ElEmpty
          v-if="rules.length === 0"
          description="当前版本暂无规则"
        />
        <ElTable
          v-else
          :data="rules"
          row-key="rule_key"
          aria-label="风险规则编辑列表"
        >
          <ElTableColumn
            label="规则键"
            min-width="180"
          >
            <template #default="scope">
              <span class="technical-value">{{ scope.row.rule_key }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="风险类型"
            min-width="160"
            prop="risk_type"
          />
          <ElTableColumn
            label="触发条件"
            min-width="260"
          >
            <template #default="scope">
              {{ conditionSummary(scope.row.condition) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="等级"
            width="90"
          >
            <template #default="scope">
              <ElTag :type="scope.row.severity === 'high' ? 'danger' : scope.row.severity === 'medium' ? 'warning' : 'info'">
                {{ severityLabel(scope.row.severity) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="110"
          >
            <template #default="scope">
              <ElSwitch
                v-model="scope.row.enabled"
                :disabled="readOnly"
                aria-label="启用规则"
              />
            </template>
          </ElTableColumn>
          <ElTableColumn
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
                @click="openExistingRule(scope.$index)"
              >
                编辑
              </ElButton>
              <ElButton
                v-if="!readOnly"
                link
                type="danger"
                :icon="Delete"
                @click="removeRule(scope.$index)"
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
          放弃本地修改
        </ElButton>
        <ElButton
          type="primary"
          :loading="saving"
          :disabled="publishing"
          @click="saveDraft"
        >
          保存草稿
        </ElButton>
        <ElButton
          type="success"
          :icon="Promotion"
          :loading="publishing"
          :disabled="saving"
          @click="publish"
        >
          发布版本
        </ElButton>
      </div>
    </template>

    <ElDrawer
      v-model="editorOpen"
      :title="editingIndex === null ? '新增规则' : '编辑规则'"
      direction="rtl"
      size="min(520px, 100vw)"
    >
      <ElForm label-position="top">
        <ElFormItem
          label="规则键"
          required
        >
          <ElInput
            v-model="ruleDraft.rule_key"
            maxlength="128"
            placeholder="例如：payment_cap"
            aria-label="规则键"
          />
        </ElFormItem>
        <ElFormItem
          label="风险类型"
          required
        >
          <ElInput
            v-model="ruleDraft.risk_type"
            maxlength="128"
            placeholder="例如：payment_terms"
            aria-label="风险类型"
          />
        </ElFormItem>
        <ElFormItem
          label="引擎"
          required
        >
          <ElSelect
            v-model="ruleDraft.engine"
            aria-label="规则引擎"
          >
            <ElOption
              label="确定性规则"
              value="deterministic"
            />
            <ElOption
              label="模型辅助"
              value="model"
            />
          </ElSelect>
        </ElFormItem>
        <RiskRuleConditionEditor
          v-model="ruleDraft.condition"
          :engine="ruleDraft.engine"
        />
        <ElFormItem
          label="风险等级"
          required
        >
          <ElSelect
            v-model="ruleDraft.severity"
            aria-label="风险等级"
          >
            <ElOption
              label="高"
              value="high"
            />
            <ElOption
              label="中"
              value="medium"
            />
            <ElOption
              label="低"
              value="low"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem
          label="建议"
          required
        >
          <ElInput
            v-model="ruleDraft.suggestion"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="输入风险处置建议"
            aria-label="风险建议"
          />
        </ElFormItem>
        <ElFormItem label="启用">
          <ElSwitch
            v-model="ruleDraft.enabled"
            aria-label="启用新规则"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="editorOpen = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          @click="saveRule"
        >
          保存到草稿
        </ElButton>
      </template>
    </ElDrawer>
  </section>
</template>
