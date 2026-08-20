<script setup lang="ts">
import { Refresh, WarningFilled } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { listWarnings } from '@/api/warnings'
import type { ContractType, WarningListItem, WarningPage, WarningSeverity, WarningStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { currentOrganizationId } from '@/features/auth/session'

const router = useRouter()
const organizationId = currentOrganizationId
const page = ref<WarningPage | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const status = ref<WarningStatus | ''>('')
const severity = ref<WarningSeverity | ''>('')
const contractType = ref<ContractType | ''>('')
const riskType = ref('')
const sort = ref<'triggered_at' | 'priority' | 'due_at'>('triggered_at')
const direction = ref<'asc' | 'desc'>('desc')
const nextCursor = ref<string | null>(null)
const items = ref<WarningListItem[]>([])
const hasMore = ref(false)
let generation = 0

const organizationMissing = computed(() => !organizationId.value)

const statusLabels: Record<WarningStatus, string> = {
  pending_confirmation: '待确认',
  in_progress: '处理中',
  ignored: '已忽略',
  resolved: '已解决',
  closed: '已关闭',
}
const severityLabels: Record<WarningSeverity, string> = { high: '高风险', medium: '中风险', low: '低风险' }

function resetError(): void {
  errorMessage.value = ''
  requestId.value = undefined
  forbidden.value = false
}

function severityType(value: WarningSeverity): 'danger' | 'warning' | 'info' {
  return value === 'high' ? 'danger' : value === 'medium' ? 'warning' : 'info'
}

function severityLabel(value: WarningSeverity): string {
  return severityLabels[value]
}

function statusLabel(value: WarningStatus): string {
  return statusLabels[value]
}

function statusType(value: WarningStatus): 'danger' | 'warning' | 'success' | 'info' {
  if (value === 'pending_confirmation') return 'danger'
  if (value === 'in_progress') return 'warning'
  if (value === 'resolved') return 'success'
  return 'info'
}

function formatDate(value: string | null): string {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

async function load(reset = true): Promise<void> {
  const requestedOrganizationId = organizationId.value
  const currentGeneration = ++generation
  resetError()
  if (!requestedOrganizationId) {
    loading.value = false
    return
  }
  loading.value = true
  if (reset) nextCursor.value = null
  try {
    const response = await listWarnings(requestedOrganizationId, {
      status: status.value || undefined,
      severity: severity.value || undefined,
      contract_type: contractType.value || undefined,
      risk_type: riskType.value.trim() || undefined,
      sort: sort.value,
      direction: direction.value,
      limit: 20,
      cursor: reset ? undefined : nextCursor.value ?? undefined,
    })
    if (currentGeneration !== generation || requestedOrganizationId !== organizationId.value) return
    page.value = response
    items.value = reset ? response.items : [...items.value, ...response.items]
    nextCursor.value = response.next_cursor
    hasMore.value = response.has_more
  } catch (error) {
    if (currentGeneration !== generation || requestedOrganizationId !== organizationId.value) return
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    if (currentGeneration === generation) loading.value = false
  }
}

function openWarning(item: WarningListItem): void {
  void router.push(`/warnings/${item.id}`)
}

onMounted(() => void load())
watch(organizationId, () => {
  items.value = []
  page.value = null
  nextCursor.value = null
  hasMore.value = false
  void load()
})
</script>

<template>
  <section class="admin-page warnings-page">
    <div class="page-heading">
      <div>
        <h1>预警中心</h1>
        <p>集中查看需要人工确认的风险、条款和低置信度结果。</p>
      </div>
      <ElButton
        :icon="Refresh"
        :loading="loading"
        @click="load()"
      >
        刷新
      </ElButton>
    </div>

    <ElResult
      v-if="organizationMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要查看的组织。"
    />
    <PageState
      v-else-if="forbidden"
      title="无法访问预警中心"
      :description="errorMessage || '当前账户没有预警访问权限。'"
      icon="error"
      :request-id="requestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="预警加载失败"
      :description="errorMessage"
      icon="error"
      :request-id="requestId"
      @retry="load()"
    />
    <template v-else>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />
      <section
        class="warning-summary"
        aria-label="预警摘要"
      >
        <div class="warning-summary-item">
          <span>未处理</span>
          <strong>{{ page?.summary.unprocessed_count ?? 0 }}</strong>
        </div>
        <div class="warning-summary-item warning-summary-item--critical">
          <span>高风险</span>
          <strong>{{ page?.summary.high_count ?? 0 }}</strong>
        </div>
      </section>
      <section
        class="filter-panel warning-filter"
        aria-label="预警筛选"
      >
        <ElSelect
          v-model="status"
          clearable
          aria-label="预警状态"
          placeholder="全部状态"
        >
          <ElOption
            label="全部状态"
            value=""
          />
          <ElOption
            v-for="(label, value) in statusLabels"
            :key="value"
            :label="label"
            :value="value"
          />
        </ElSelect>
        <ElSelect
          v-model="severity"
          clearable
          aria-label="风险等级"
          placeholder="全部等级"
        >
          <ElOption
            label="全部等级"
            value=""
          />
          <ElOption
            v-for="(label, value) in severityLabels"
            :key="value"
            :label="label"
            :value="value"
          />
        </ElSelect>
        <ElSelect
          v-model="contractType"
          clearable
          aria-label="合同类型"
          placeholder="全部合同类型"
        >
          <ElOption
            label="全部合同类型"
            value=""
          />
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
            label="其他"
            value="other"
          />
        </ElSelect>
        <ElInput
          v-model="riskType"
          clearable
          aria-label="风险类型"
          placeholder="风险类型"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="sort"
          aria-label="预警排序"
        >
          <ElOption
            label="触发时间"
            value="triggered_at"
          />
          <ElOption
            label="优先级"
            value="priority"
          />
          <ElOption
            label="截止时间"
            value="due_at"
          />
        </ElSelect>
        <ElSelect
          v-model="direction"
          aria-label="排序方向"
        >
          <ElOption
            label="降序"
            value="desc"
          />
          <ElOption
            label="升序"
            value="asc"
          />
        </ElSelect>
        <ElButton
          :icon="Refresh"
          :loading="loading"
          @click="load()"
        >
          应用筛选
        </ElButton>
      </section>
      <section class="table-panel">
        <ElSkeleton
          v-if="loading && items.length === 0"
          :rows="6"
          animated
          class="table-skeleton"
        />
        <ElEmpty
          v-else-if="items.length === 0"
          description="暂无预警"
        />
        <ElTable
          v-else
          v-loading="loading"
          :data="items"
          row-key="id"
          aria-label="预警列表"
          @row-click="openWarning"
        >
          <ElTableColumn
            label="风险等级"
            width="130"
          >
            <template #default="scope">
              <ElTag :type="severityType(scope.row.severity)">
                {{ severityLabel(scope.row.severity) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="触发类型"
            min-width="180"
          >
            <template #default="scope">
              <button
                class="table-link"
                type="button"
                @click.stop="openWarning(scope.row)"
              >
                {{ scope.row.trigger_type }}
              </button>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="130"
          >
            <template #default="scope">
              <ElTag :type="statusType(scope.row.status)">
                {{ statusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="责任人"
            min-width="150"
          >
            <template #default="scope">
              <span class="technical-value">{{ scope.row.assignee_id ? scope.row.assignee_id.slice(0, 8) : '未分派' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="截止时间"
            min-width="180"
          >
            <template #default="scope">
              {{ formatDate(scope.row.due_at) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="触发时间"
            min-width="180"
          >
            <template #default="scope">
              {{ formatDate(scope.row.triggered_at) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="110"
            align="right"
          >
            <template #default="scope">
              <ElButton
                link
                type="primary"
                @click.stop="openWarning(scope.row)"
              >
                <ElIcon><WarningFilled /></ElIcon>查看
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div
          v-if="items.length > 0"
          class="table-footer"
        >
          <span>{{ items.length }} 条预警</span>
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
  </section>
</template>
