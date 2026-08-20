<script setup lang="ts">
import { Plus, Refresh, Switch } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createRiskRuleBundle,
  listRiskRuleBundles,
  updateRiskRuleBundle,
} from '@/api/riskRules'
import type { RiskRuleBundle, RiskRuleBundleStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { currentOrganizationId, currentOrganizationMembership } from '@/features/auth/session'

const router = useRouter()
const organizationId = currentOrganizationId
const role = computed(() => currentOrganizationMembership.value?.role)
const canManage = computed(() => role.value === 'org_admin')

const items = ref<RiskRuleBundle[]>([])
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const search = ref('')
const status = ref<RiskRuleBundleStatus | ''>('')
const createOpen = ref(false)
const createName = ref('')
const creating = ref(false)
const createError = ref('')
const createRequestId = ref<string>()
const createIdempotencyKey = ref('')
const switchingBundleId = ref<string | null>(null)
let loadGeneration = 0

const organizationContextMissing = computed(() => !organizationId.value)

function statusLabel(value: RiskRuleBundleStatus): string {
  return value === 'active' ? '启用' : '已停用'
}

function versionLabel(item: RiskRuleBundle): string {
  return item.current_published_version_id ? item.current_published_version_id.slice(0, 8) : '未发布'
}

function resetPageError(): void {
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
}

async function load(reset = true): Promise<void> {
  const generation = ++loadGeneration
  const requestedOrganizationId = organizationId.value
  resetPageError()
  if (!requestedOrganizationId) {
    loading.value = false
    return
  }
  loading.value = true
  if (reset) nextCursor.value = null
  try {
    const page = await listRiskRuleBundles(requestedOrganizationId, {
      q: search.value.trim() || undefined,
      status: status.value || undefined,
      limit: 20,
      cursor: reset ? undefined : nextCursor.value ?? undefined,
    })
    if (generation !== loadGeneration || requestedOrganizationId !== organizationId.value) return
    items.value = reset ? page.items : [...items.value, ...page.items]
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
  } catch (error) {
    if (generation !== loadGeneration || requestedOrganizationId !== organizationId.value) return
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function openCreate(): void {
  createName.value = ''
  createError.value = ''
  createRequestId.value = undefined
  createIdempotencyKey.value = crypto.randomUUID()
  createOpen.value = true
}

async function submitCreate(): Promise<void> {
  const requestedOrganizationId = organizationId.value
  if (!requestedOrganizationId || !createName.value.trim() || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    const bundle = await createRiskRuleBundle(
      requestedOrganizationId,
      { name: createName.value.trim() },
      createIdempotencyKey.value,
    )
    createOpen.value = false
    createIdempotencyKey.value = ''
    await router.push(`/risk-rule-bundles/${bundle.id}`)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    createError.value = safe.message
    createRequestId.value = safe.requestId
  } finally {
    creating.value = false
  }
}

async function switchDefault(bundle: RiskRuleBundle): Promise<void> {
  if (
    !organizationId.value ||
    !canManage.value ||
    bundle.is_default ||
    bundle.status !== 'active' ||
    !bundle.current_published_version_id ||
    switchingBundleId.value
  ) {
    return
  }
  try {
    await ElMessageBox.confirm(
      '切换后组织审核将使用此规则集的当前发布版本。确定设为默认吗？',
      '确认切换默认规则集',
      { type: 'warning', confirmButtonText: '切换', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  switchingBundleId.value = bundle.id
  resetPageError()
  try {
    await updateRiskRuleBundle(bundle.id, {
      is_default: true,
      version: bundle.version,
    })
    await load()
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
  } finally {
    switchingBundleId.value = null
  }
}

function openBundle(bundle: RiskRuleBundle): void {
  void router.push(`/risk-rule-bundles/${bundle.id}`)
}

function handleCreateError(): void {
  if (createError.value) ElMessage.error(createError.value)
}

onMounted(() => void load())

watch(organizationId, () => {
  loadGeneration += 1
  items.value = []
  nextCursor.value = null
  hasMore.value = false
  void load()
})
</script>

<template>
  <section class="admin-page risk-rules-page">
    <div class="page-heading">
      <div>
        <h1>风险规则</h1>
        <p>维护组织风险规则集、默认基线和发布版本。</p>
      </div>
      <ElButton
        v-if="canManage"
        type="primary"
        :icon="Plus"
        @click="openCreate"
      >
        新建规则集
      </ElButton>
    </div>

    <ElResult
      v-if="organizationContextMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问风险规则"
      :description="errorMessage || '当前账户没有风险规则访问权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="风险规则加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <template v-else>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      >
        <p
          v-if="errorRequestId"
          class="request-id"
        >
          请求 ID：{{ errorRequestId }}
        </p>
      </ElAlert>
      <section
        class="filter-panel risk-rules-filter"
        aria-label="风险规则筛选"
      >
        <ElInput
          v-model="search"
          clearable
          placeholder="搜索规则集名称"
          aria-label="搜索规则集"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="status"
          aria-label="规则集状态"
        >
          <ElOption
            label="全部状态"
            value=""
          />
          <ElOption
            label="启用"
            value="active"
          />
          <ElOption
            label="已停用"
            value="disabled"
          />
        </ElSelect>
        <ElButton
          :icon="Refresh"
          :loading="loading"
          :disabled="loading"
          @click="load()"
        >
          应用筛选
        </ElButton>
      </section>

      <section class="table-panel">
        <ElSkeleton
          v-if="loading && items.length === 0"
          :rows="5"
          animated
          class="table-skeleton"
        />
        <ElEmpty
          v-else-if="items.length === 0"
          description="暂无风险规则集"
        >
          <ElButton
            v-if="canManage"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            创建第一套规则
          </ElButton>
        </ElEmpty>
        <ElTable
          v-else
          v-loading="loading"
          :data="items"
          row-key="id"
          aria-label="风险规则集列表"
          @row-click="openBundle"
        >
          <ElTableColumn
            label="规则集名称"
            min-width="240"
          >
            <template #default="scope">
              <button
                class="table-link"
                type="button"
                @click.stop="openBundle(scope.row)"
              >
                {{ scope.row.name }}
              </button>
              <ElTag
                v-if="scope.row.is_default"
                size="small"
                type="success"
                class="table-inline-tag"
              >
                默认
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="当前发布版本"
            min-width="190"
          >
            <template #default="scope">
              <span class="technical-value">{{ versionLabel(scope.row) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="120"
          >
            <template #default="scope">
              <ElTag :type="scope.row.status === 'active' ? 'success' : 'info'">
                {{ statusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="资源版本"
            width="110"
          >
            <template #default="scope">
              <span class="technical-value">v{{ scope.row.version }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="240"
            align="right"
          >
            <template #default="scope">
              <ElButton
                link
                type="primary"
                @click.stop="openBundle(scope.row)"
              >
                查看详情
              </ElButton>
              <ElButton
                v-if="canManage && scope.row.status === 'active' && !scope.row.is_default && scope.row.current_published_version_id"
                link
                type="warning"
                :icon="Switch"
                :loading="switchingBundleId === scope.row.id"
                :disabled="switchingBundleId !== null"
                @click.stop="switchDefault(scope.row)"
              >
                设为默认
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div
          v-if="items.length > 0"
          class="table-footer"
        >
          <span>{{ items.length }} 个规则集</span>
          <ElButton
            v-if="hasMore"
            :loading="loading"
            @click="load(false)"
          >
            加载更多
          </ElButton>
        </div>
      </section>
    </template>

    <ElDialog
      v-model="createOpen"
      title="新建规则集"
      width="min(520px, calc(100vw - 32px))"
      @close="handleCreateError"
    >
      <ElAlert
        v-if="createError"
        :title="createError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        <p
          v-if="createRequestId"
          class="request-id"
        >
          请求 ID：{{ createRequestId }}
        </p>
      </ElAlert>
      <ElForm label-position="top">
        <ElFormItem
          label="规则集名称"
          required
        >
          <ElInput
            v-model="createName"
            maxlength="255"
            show-word-limit
            placeholder="例如：采购合同风险基线"
            aria-label="规则集名称"
            @keyup.enter="submitCreate"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createOpen = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="creating"
          :disabled="!createName.trim()"
          @click="submitCreate"
        >
          创建
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
