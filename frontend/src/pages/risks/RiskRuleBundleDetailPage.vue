<script setup lang="ts">
import { ArrowLeft, Edit, Plus, Switch } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createRiskRuleVersion,
  getRiskRuleBundle,
  updateRiskRuleBundle,
} from '@/api/riskRules'
import type {
  RiskRuleInput,
  RiskRuleBundleDetail,
  RiskRuleVersionSummary,
} from '@/api/types'
import RiskRuleConditionEditor from '@/components/RiskRuleConditionEditor.vue'
import PageState from '@/components/PageState.vue'
import {
  activeOrganizationMemberships,
  selectCurrentOrganization,
} from '@/features/auth/session'
import {
  normalizeRiskRule,
  validateRiskRules,
} from '@/features/risk-rules/validation'

const route = useRoute()
const router = useRouter()
const bundleId = computed(() => String(route.params.bundleId ?? ''))

const bundle = ref<RiskRuleBundleDetail | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string>()
const creatingDraft = ref(false)
const draftDialogOpen = ref(false)
const draftNote = ref('')
const draftRules = ref<RiskRuleInput[]>([])
const draftIdempotencyKey = ref('')
const identityDialogOpen = ref(false)
const identityName = ref('')
const updatingIdentity = ref(false)
const bundleAction = ref<'default' | 'disable' | 'enable' | null>(null)
const resourceOrganizationId = computed(() => bundle.value?.organization_id ?? '')
const resourceMembership = computed(() =>
  activeOrganizationMemberships.value.find(
    (membership) => membership.organization_id === resourceOrganizationId.value,
  ),
)
const canManage = computed(() => resourceMembership.value?.role === 'org_admin')
const organizationContextMissing = computed(
  () => activeOrganizationMemberships.value.length === 0,
)
let loadGeneration = 0

const currentPublishedVersion = computed(() =>
  bundle.value?.versions.find((version) => version.id === bundle.value?.current_published_version_id),
)
const hasPublishedRules = computed(() => Boolean(currentPublishedVersion.value?.rules?.length))

function statusLabel(value: RiskRuleBundleDetail['status']): string {
  return value === 'active' ? '启用' : '已停用'
}

function versionStatusLabel(value: RiskRuleVersionSummary['status']): string {
  return value === 'published' ? '已发布' : '草稿'
}

function formatDate(value: string | null): string {
  if (!value) return '未发布'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function rulePayload(rule: RiskRuleInput): RiskRuleInput {
  return normalizeRiskRule(rule)
}

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

function setActionError(error: unknown): void {
  if (typeof error === 'string') {
    actionError.value = error
    actionRequestId.value = undefined
    return
  }
  const safe = toSafeDisplayError(error)
  actionError.value = safe.message
  actionRequestId.value = safe.requestId
}

async function load(): Promise<void> {
  const generation = ++loadGeneration
  const requestedBundleId = bundleId.value
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  actionError.value = ''
  actionRequestId.value = undefined
  if (!requestedBundleId) {
    bundle.value = null
    loading.value = false
    return
  }
  loading.value = true
  try {
    const loaded = await getRiskRuleBundle(requestedBundleId, true)
    if (
      generation !== loadGeneration ||
      requestedBundleId !== bundleId.value
    ) {
      return
    }
    bundle.value = loaded
    selectCurrentOrganization(loaded.organization_id)
  } catch (error) {
    if (generation !== loadGeneration) return
    setPageError(error)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function openVersion(version: RiskRuleVersionSummary): void {
  void router.push(`/risk-rule-bundle-versions/${version.id}`)
}

function blankRule(): RiskRuleInput {
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

function rulesForDraft(): RiskRuleInput[] {
  return draftRules.value.map(rulePayload)
}

function openDraftDialog(): void {
  draftNote.value = ''
  actionError.value = ''
  draftRules.value = hasPublishedRules.value
    ? (currentPublishedVersion.value?.rules ?? []).map(rulePayload)
    : [blankRule()]
  draftIdempotencyKey.value = crypto.randomUUID()
  draftDialogOpen.value = true
}

function openIdentityDialog(): void {
  if (!bundle.value || !canManage.value) return
  identityName.value = bundle.value.name
  actionError.value = ''
  identityDialogOpen.value = true
}

async function saveIdentity(): Promise<void> {
  if (!bundle.value || !canManage.value || !identityName.value.trim() || updatingIdentity.value) {
    return
  }
  updatingIdentity.value = true
  actionError.value = ''
  try {
    await updateRiskRuleBundle(bundle.value.id, {
      name: identityName.value.trim(),
      version: bundle.value.version,
    })
    identityDialogOpen.value = false
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      await load()
      setActionError(error)
    } else {
      setActionError(error)
    }
  } finally {
    updatingIdentity.value = false
  }
}

async function createDraft(): Promise<void> {
  if (!bundle.value || !canManage.value || !draftNote.value.trim() || creatingDraft.value) return
  const validationError = validateRiskRules(draftRules.value)
  if (validationError) {
    setActionError(validationError)
    return
  }
  creatingDraft.value = true
  actionError.value = ''
  try {
    const version = await createRiskRuleVersion(
      bundle.value.id,
      {
        change_note: draftNote.value.trim(),
        source_version_id: currentPublishedVersion.value?.id,
        rules: rulesForDraft(),
      },
      draftIdempotencyKey.value,
    )
    draftDialogOpen.value = false
    draftIdempotencyKey.value = ''
    await router.push(`/risk-rule-bundle-versions/${version.id}`)
  } catch (error) {
    setActionError(error)
  } finally {
    creatingDraft.value = false
  }
}

async function switchDefault(): Promise<void> {
  if (!bundle.value || !canManage.value || bundle.value.is_default || bundleAction.value) return
  bundleAction.value = 'default'
  try {
    try {
      await ElMessageBox.confirm(
        '切换后该组织的审核任务将使用此规则集的当前发布版本。确定切换默认规则集吗？',
        '确认切换默认规则集',
        { type: 'warning', confirmButtonText: '切换', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    actionError.value = ''
    try {
      await updateRiskRuleBundle(bundle.value.id, {
        is_default: true,
        version: bundle.value.version,
      })
      await load()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await load()
        setActionError(error)
      } else {
        setActionError(error)
      }
    }
  } finally {
    bundleAction.value = null
  }
}

async function disableBundle(): Promise<void> {
  if (!bundle.value || !canManage.value || bundle.value.status === 'disabled' || bundleAction.value) {
    return
  }
  bundleAction.value = 'disable'
  try {
    try {
      await ElMessageBox.confirm(
        '停用后不能创建或发布新版本；当前默认规则集必须先切换。确定停用吗？',
        '确认停用规则集',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    actionError.value = ''
    try {
      await updateRiskRuleBundle(bundle.value.id, {
        status: 'disabled',
        version: bundle.value.version,
      })
      await load()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await load()
        setActionError(error)
      } else {
        setActionError(error)
      }
    }
  } finally {
    bundleAction.value = null
  }
}

async function enableBundle(): Promise<void> {
  if (!bundle.value || !canManage.value || bundle.value.status !== 'disabled' || bundleAction.value) {
    return
  }
  bundleAction.value = 'enable'
  actionError.value = ''
  try {
    await updateRiskRuleBundle(bundle.value.id, {
      status: 'active',
      version: bundle.value.version,
    })
    await load()
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      await load()
      setActionError(error)
    } else {
      setActionError(error)
    }
  } finally {
    bundleAction.value = null
  }
}

onMounted(() => void load())

watch(bundleId, () => {
  bundle.value = null
  void load()
})
</script>

<template>
  <section class="admin-page risk-rule-detail-page">
    <button
      class="back-link"
      type="button"
      @click="router.push('/risk-rule-bundles')"
    >
      <ElIcon><ArrowLeft /></ElIcon>
      返回风险规则
    </button>

    <ElResult
      v-if="organizationContextMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问规则集"
      :description="errorMessage || '规则集不存在或当前账户没有访问权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!bundle && (errorMessage || !loading)"
      title="规则集详情加载失败"
      :description="errorMessage || '规则集不存在。'"
      :request-id="errorRequestId"
      @retry="load"
    />
    <ElSkeleton
      v-else-if="loading"
      :rows="8"
      animated
      class="table-skeleton"
    />
    <template v-else-if="bundle">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            规则集 · {{ bundle.id }}
          </div>
          <h1>{{ bundle.name }}</h1>
          <p>资源版本 v{{ bundle.version }} · 当前发布版本 {{ currentPublishedVersion?.version_no ? `v${currentPublishedVersion.version_no}` : '未发布' }}</p>
        </div>
        <div class="page-heading-actions">
          <ElTag
            :type="bundle.status === 'active' ? 'success' : 'info'"
            size="large"
          >
            {{ statusLabel(bundle.status) }}
          </ElTag>
          <ElTag
            v-if="bundle.is_default"
            type="success"
            size="large"
          >
            默认规则集
          </ElTag>
        </div>
      </div>

      <ElAlert
        v-if="actionError && !draftDialogOpen && !identityDialogOpen"
        :title="actionError"
        type="error"
        :closable="false"
        show-icon
      >
        <p
          v-if="actionRequestId"
          class="request-id"
        >
          请求 ID：{{ actionRequestId }}
        </p>
      </ElAlert>

      <section class="summary-panel rule-bundle-summary">
        <div class="section-heading">
          <div>
            <h2>规则集概览</h2>
            <p>默认标识只由组织管理员显式切换，发布版本不会自动替换其他默认规则集。</p>
          </div>
          <div class="page-heading-actions">
            <ElButton
              v-if="canManage"
              :icon="Edit"
              :disabled="bundleAction !== null"
              @click="openIdentityDialog"
            >
              编辑规则集
            </ElButton>
            <ElButton
              v-if="canManage && !bundle.is_default && bundle.status === 'active' && bundle.current_published_version_id"
              :icon="Switch"
              :loading="bundleAction === 'default'"
              :disabled="bundleAction !== null && bundleAction !== 'default'"
              @click="switchDefault"
            >
              设为默认
            </ElButton>
            <ElButton
              v-if="canManage && bundle.status === 'active'"
              type="danger"
              plain
              :loading="bundleAction === 'disable'"
              :disabled="bundle.is_default || (bundleAction !== null && bundleAction !== 'disable')"
              title="当前默认规则集必须先切换默认项"
              @click="disableBundle"
            >
              停用规则集
            </ElButton>
            <ElButton
              v-if="canManage && bundle.status === 'active'"
              type="primary"
              :icon="Plus"
              :disabled="bundleAction !== null"
              @click="openDraftDialog"
            >
              新建草稿
            </ElButton>
            <ElButton
              v-if="canManage && bundle.status === 'disabled'"
              type="primary"
              :loading="bundleAction === 'enable'"
              :disabled="bundleAction !== null && bundleAction !== 'enable'"
              @click="enableBundle"
            >
              重新启用
            </ElButton>
          </div>
        </div>
        <p
          v-if="canManage && bundle.is_default && bundle.status === 'active'"
          class="action-hint"
        >
          当前默认规则集不能直接停用，请先将另一个已发布规则集设为默认。
        </p>
        <dl class="metadata-list">
          <div>
            <dt>当前发布版本</dt>
            <dd class="technical-value">
              {{ bundle.current_published_version_id || '未发布' }}
            </dd>
          </div>
          <div>
            <dt>默认选择</dt>
            <dd>{{ bundle.is_default ? '组织当前默认' : '不是组织当前默认' }}</dd>
          </div>
          <div>
            <dt>版本数量</dt>
            <dd>{{ bundle.versions.length }}</dd>
          </div>
          <div>
            <dt>规则集状态</dt>
            <dd>{{ statusLabel(bundle.status) }}</dd>
          </div>
        </dl>
      </section>

      <section class="table-panel">
        <div class="section-heading rule-history-heading">
          <div>
            <h2>版本历史</h2>
            <p>已发布版本不可编辑，历史审核继续引用原版本。</p>
          </div>
        </div>
        <ElEmpty
          v-if="bundle.versions.length === 0"
          description="暂无版本"
        />
        <ElTable
          v-else
          :data="bundle.versions"
          row-key="id"
          aria-label="风险规则版本历史"
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
            min-width="280"
            prop="change_note"
          />
          <ElTableColumn
            label="规则数"
            width="100"
            prop="rule_count"
          />
          <ElTableColumn
            label="生效时间"
            width="190"
          >
            <template #default="scope">
              {{ formatDate(scope.row.effective_at) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="130"
            align="right"
          >
            <template #default="scope">
              <ElButton
                link
                type="primary"
                :icon="scope.row.status === 'draft' ? Edit : undefined"
                @click.stop="openVersion(scope.row)"
              >
                {{ scope.row.status === 'draft' ? '编辑草稿' : '查看版本' }}
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </section>

      <section
        v-if="currentPublishedVersion?.rules?.length"
        class="table-panel rule-preview-panel"
      >
        <div class="section-heading rule-history-heading">
          <div>
            <h2>当前版本规则预览</h2>
            <p>结构化条件仅使用服务端白名单 Schema。</p>
          </div>
        </div>
        <ElTable
          :data="currentPublishedVersion.rules"
          row-key="rule_key"
          aria-label="当前版本规则预览"
        >
          <ElTableColumn
            label="规则键"
            min-width="180"
            prop="rule_key"
          />
          <ElTableColumn
            label="风险类型"
            min-width="180"
            prop="risk_type"
          />
          <ElTableColumn
            label="引擎"
            width="130"
            prop="engine"
          />
          <ElTableColumn
            label="等级"
            width="100"
            prop="severity"
          />
          <ElTableColumn
            label="启用"
            width="100"
          >
            <template #default="scope">
              {{ scope.row.enabled ? '是' : '否' }}
            </template>
          </ElTableColumn>
        </ElTable>
      </section>
    </template>

    <ElDialog
      v-model="draftDialogOpen"
      title="新建规则草稿"
      width="min(640px, calc(100vw - 32px))"
    >
      <p class="dialog-context">
        {{ hasPublishedRules ? '将从当前发布版本复制规则。' : '请先定义首条规则，创建后可继续添加和调整。' }}
        创建后可在草稿编辑器中逐条调整，发布前不会影响现行基线。
      </p>
      <ElAlert
        v-if="actionError"
        :title="actionError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        <p
          v-if="actionRequestId"
          class="request-id"
        >
          请求 ID：{{ actionRequestId }}
        </p>
      </ElAlert>
      <ElForm label-position="top">
        <ElFormItem
          label="变更说明"
          required
        >
          <ElInput
            v-model="draftNote"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="说明本次规则更新的目的和范围"
            aria-label="变更说明"
          />
        </ElFormItem>
        <template v-if="!hasPublishedRules && draftRules[0]">
          <h3 class="dialog-section-title">
            首条规则
          </h3>
          <ElFormItem
            label="规则键"
            required
          >
            <ElInput
              v-model="draftRules[0].rule_key"
              maxlength="128"
              placeholder="例如：payment_cap"
              aria-label="首条规则键"
            />
          </ElFormItem>
          <ElFormItem
            label="风险类型"
            required
          >
            <ElInput
              v-model="draftRules[0].risk_type"
              maxlength="128"
              placeholder="例如：payment_terms"
              aria-label="首条风险类型"
            />
          </ElFormItem>
          <ElFormItem
            label="引擎"
            required
          >
            <ElSelect
              v-model="draftRules[0].engine"
              aria-label="首条规则引擎"
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
          <ElFormItem
            label="条件"
            required
          >
            <RiskRuleConditionEditor
              v-model="draftRules[0].condition"
              :engine="draftRules[0].engine"
            />
          </ElFormItem>
          <ElFormItem
            label="风险等级"
            required
          >
            <ElSelect
              v-model="draftRules[0].severity"
              aria-label="首条风险等级"
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
              v-model="draftRules[0].suggestion"
              type="textarea"
              :rows="3"
              maxlength="2000"
              show-word-limit
              placeholder="输入风险处置建议"
              aria-label="首条风险建议"
            />
          </ElFormItem>
        </template>
      </ElForm>
      <template #footer>
        <ElButton @click="draftDialogOpen = false">
          取消
        </ElButton>
        <ElButton
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
      v-model="identityDialogOpen"
      title="编辑规则集"
      width="min(520px, calc(100vw - 32px))"
    >
      <ElAlert
        v-if="actionError"
        :title="actionError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        <p
          v-if="actionRequestId"
          class="request-id"
        >
          请求 ID：{{ actionRequestId }}
        </p>
      </ElAlert>
      <ElForm label-position="top">
        <ElFormItem
          label="规则集名称"
          required
        >
          <ElInput
            v-model="identityName"
            maxlength="255"
            show-word-limit
            aria-label="规则集名称"
            @keyup.enter="saveIdentity"
          />
        </ElFormItem>
        <p class="dialog-context">
          规则内容只能通过创建新版本修改；已发布版本不会被此操作改变。
        </p>
      </ElForm>
      <template #footer>
        <ElButton @click="identityDialogOpen = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="updatingIdentity"
          :disabled="!identityName.trim()"
          @click="saveIdentity"
        >
          保存
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
