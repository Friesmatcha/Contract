<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getReviewMetrics, getWarningMetrics } from '@/api/operations'
import type { ContractType, ReviewMetrics, WarningMetrics } from '@/api/types'
import { activeOrganizationMemberships } from '@/features/auth/session'
import PageState from '@/components/PageState.vue'

const review = ref<ReviewMetrics | null>(null)
const warnings = ref<WarningMetrics | null>(null)
const loading = ref(true)
const reviewLoading = ref(false)
const warningLoading = ref(false)
const reviewError = ref('')
const warningError = ref('')
const reviewRequestId = ref<string>()
const warningRequestId = ref<string>()
const forbidden = ref(false)
const from = ref('')
const to = ref('')
const contractType = ref<ContractType | ''>('')
const riskType = ref('')
const severity = ref<'high' | 'medium' | 'low' | ''>('')

const route = useRoute()
const organizationId = computed(() => String(route.params.organizationId ?? ''))
const isAdmin = computed(() => activeOrganizationMemberships.value.some(
  (membership) => membership.organization_id === organizationId.value && membership.role === 'org_admin',
))
const dateError = computed(() => {
  if (!from.value || !to.value) return '请选择完整的开始和结束时间。'
  const start = new Date(from.value)
  const end = new Date(to.value)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return '时间范围无效。'
  return start >= end ? '开始时间必须早于结束时间。' : ''
})
const hasData = computed(() => Boolean(review.value || warnings.value))

function localDateTime(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function setDefaultRange(): void {
  const end = new Date()
  const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000)
  from.value = localDateTime(start)
  to.value = localDateTime(end)
}

function toIso(value: string): string {
  return new Date(value).toISOString()
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function duration(value: number): string {
  if (value < 1000) return `${value} ms`
  if (value < 60_000) return `${(value / 1000).toFixed(1)} 秒`
  return `${(value / 60_000).toFixed(1)} 分钟`
}

function errorState(error: unknown): { message: string; requestId?: string; forbidden: boolean; disabled: boolean } {
  const safe = toSafeDisplayError(error)
  return {
    message: safe.message,
    requestId: safe.requestId,
    forbidden: error instanceof ApiError && (error.status === 403 || error.status === 404),
    disabled: error instanceof ApiError && error.code === 'METRICS_NOT_ENABLED',
  }
}

async function loadReview(fromIso: string, toIsoValue: string): Promise<void> {
  reviewLoading.value = true
  reviewError.value = ''
  reviewRequestId.value = undefined
  try {
    review.value = await getReviewMetrics({
      organizationId: organizationId.value,
      from: fromIso,
      to: toIsoValue,
      contractType: contractType.value || undefined,
    })
  } catch (error) {
    const state = errorState(error)
    reviewError.value = state.disabled ? '运营指标尚未启用。' : state.message
    reviewRequestId.value = state.requestId
    forbidden.value ||= state.forbidden
  } finally {
    reviewLoading.value = false
  }
}

async function loadWarnings(fromIso: string, toIsoValue: string): Promise<void> {
  warningLoading.value = true
  warningError.value = ''
  warningRequestId.value = undefined
  try {
    warnings.value = await getWarningMetrics({
      organizationId: organizationId.value,
      from: fromIso,
      to: toIsoValue,
      riskType: riskType.value.trim() || undefined,
      severity: severity.value || undefined,
    })
  } catch (error) {
    const state = errorState(error)
    warningError.value = state.disabled ? '运营指标尚未启用。' : state.message
    warningRequestId.value = state.requestId
    forbidden.value ||= state.forbidden
  } finally {
    warningLoading.value = false
  }
}

async function load(): Promise<void> {
  if (dateError.value || !organizationId.value || loading.value && hasData.value) return
  loading.value = true
  forbidden.value = false
  const fromIso = toIso(from.value)
  const toIsoValue = toIso(to.value)
  await Promise.all([loadReview(fromIso, toIsoValue), loadWarnings(fromIso, toIsoValue)])
  loading.value = false
}

function retryReview(): void {
  if (dateError.value) return
  void loadReview(toIso(from.value), toIso(to.value))
}

function retryWarnings(): void {
  if (dateError.value) return
  void loadWarnings(toIso(from.value), toIso(to.value))
}

function reset(): void {
  setDefaultRange()
  contractType.value = ''
  riskType.value = ''
  severity.value = ''
  void load()
}

onMounted(() => {
  setDefaultRange()
  void load()
})

watch(organizationId, (nextOrganizationId, previousOrganizationId) => {
  if (!nextOrganizationId || nextOrganizationId === previousOrganizationId) return
  review.value = null
  warnings.value = null
  void load()
})
</script>

<template>
  <section class="admin-page operations-metrics-page">
    <PageState
      v-if="forbidden"
      title="无法查看运营指标"
      description="只有组织管理员可以查看当前组织的运营指标。"
      icon="error"
      :request-id="reviewRequestId || warningRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="!loading && !hasData && reviewError && warningError && reviewError !== '运营指标尚未启用。'"
      title="运营指标加载失败"
      description="请稍后重试两个指标接口。"
      :request-id="reviewRequestId || warningRequestId"
      @retry="load"
    />
    <template v-else>
      <div class="page-heading operations-heading">
        <div>
          <div class="technical-value">
            ADMIN-002
          </div>
          <h1>运营指标</h1>
          <p>按选定时间范围查看审核与预警运营表现。</p>
        </div>
      </div>

      <ElAlert
        v-if="dateError"
        :title="dateError"
        type="warning"
        :closable="false"
        show-icon
      />
      <section
        class="filter-panel operations-filter"
        aria-label="运营指标筛选"
      >
        <ElInput
          v-model="from"
          type="datetime-local"
          aria-label="开始时间"
        />
        <ElInput
          v-model="to"
          type="datetime-local"
          aria-label="结束时间"
        />
        <ElSelect
          v-model="contractType"
          clearable
          placeholder="合同类型"
          aria-label="合同类型"
        >
          <ElOption
            label="采购合同"
            value="purchase"
          />
          <ElOption
            label="销售合同"
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
            label="劳动合同"
            value="employment"
          />
          <ElOption
            label="其他合同"
            value="other"
          />
        </ElSelect>
        <ElInput
          v-model="riskType"
          clearable
          placeholder="风险类型"
          aria-label="风险类型"
        />
        <ElSelect
          v-model="severity"
          clearable
          placeholder="严重度"
          aria-label="严重度"
        >
          <ElOption
            label="高风险"
            value="high"
          />
          <ElOption
            label="中风险"
            value="medium"
          />
          <ElOption
            label="低风险"
            value="low"
          />
        </ElSelect>
        <ElButton
          type="primary"
          :icon="Search"
          :disabled="Boolean(dateError) || !isAdmin"
          :loading="loading"
          @click="load"
        >
          查询
        </ElButton>
        <ElButton
          :icon="Refresh"
          :disabled="loading"
          @click="reset"
        >
          重置
        </ElButton>
      </section>

      <section
        class="metrics-section"
        aria-labelledby="review-metrics-heading"
      >
        <div class="section-heading">
          <div>
            <h2 id="review-metrics-heading">
              审核指标
            </h2><p>按审核任务创建时间统计，比例为 0 到 1 的百分比展示。</p>
          </div>
        </div>
        <ElSkeleton
          v-if="reviewLoading && !review"
          :rows="3"
          animated
        />
        <ElAlert
          v-else-if="reviewError"
          :title="reviewError"
          :description="reviewRequestId ? `请求 ID：${reviewRequestId}` : undefined"
          :type="reviewError === '运营指标尚未启用。' ? 'info' : 'error'"
          :closable="false"
          show-icon
        >
          <template #default>
            <ElButton
              v-if="reviewError !== '运营指标尚未启用。'"
              link
              type="primary"
              @click="retryReview"
            >
              重试
            </ElButton>
          </template>
        </ElAlert>
        <ElEmpty
          v-else-if="review && review.review_count === 0"
          description="当前范围暂无审核事实"
        />
        <div
          v-else-if="review"
          class="metric-grid"
        >
          <div class="metric-cell">
            <span>审核总数</span><strong>{{ review.review_count }}</strong>
          </div>
          <div class="metric-cell">
            <span>已完成</span><strong>{{ review.completed_count }}</strong>
          </div>
          <div class="metric-cell">
            <span>失败</span><strong>{{ review.failed_count }}</strong>
          </div>
          <div class="metric-cell">
            <span>平均耗时</span><strong>{{ duration(review.average_duration_ms) }}</strong>
          </div>
          <div class="metric-cell">
            <span>解析失败率</span><strong>{{ percent(review.parse_failure_rate) }}</strong>
          </div>
          <div class="metric-cell">
            <span>模型失败率</span><strong>{{ percent(review.model_failure_rate) }}</strong>
          </div>
          <div class="metric-cell">
            <span>人工编辑率</span><strong>{{ percent(review.manual_edit_rate) }}</strong>
          </div>
        </div>
      </section>

      <section
        class="metrics-section"
        aria-labelledby="warning-metrics-heading"
      >
        <div class="section-heading">
          <div>
            <h2 id="warning-metrics-heading">
              预警指标
            </h2><p>按预警触发时间统计当前处置状态。</p>
          </div>
        </div>
        <ElSkeleton
          v-if="warningLoading && !warnings"
          :rows="3"
          animated
        />
        <ElAlert
          v-else-if="warningError"
          :title="warningError"
          :description="warningRequestId ? `请求 ID：${warningRequestId}` : undefined"
          :type="warningError === '运营指标尚未启用。' ? 'info' : 'error'"
          :closable="false"
          show-icon
        >
          <template #default>
            <ElButton
              v-if="warningError !== '运营指标尚未启用。'"
              link
              type="primary"
              @click="retryWarnings"
            >
              重试
            </ElButton>
          </template>
        </ElAlert>
        <ElEmpty
          v-else-if="warnings && warnings.created_count === 0"
          description="当前范围暂无预警事实"
        />
        <template v-else-if="warnings">
          <div class="metric-grid warning-metric-grid">
            <div class="metric-cell">
              <span>创建数</span><strong>{{ warnings.created_count }}</strong>
            </div>
            <div class="metric-cell">
              <span>未处理</span><strong>{{ warnings.unprocessed_count }}</strong>
            </div>
            <div class="metric-cell">
              <span>已关闭</span><strong>{{ warnings.closed_count }}</strong>
            </div>
            <div class="metric-cell">
              <span>关闭率</span><strong>{{ percent(warnings.closure_rate) }}</strong>
            </div>
            <div class="metric-cell">
              <span>误报率</span><strong>{{ percent(warnings.false_positive_rate) }}</strong>
            </div>
            <div class="metric-cell">
              <span>平均未处理时长</span><strong>{{ duration(warnings.average_unprocessed_duration_ms) }}</strong>
            </div>
          </div>
          <section class="table-panel metrics-breakdown-panel">
            <div class="section-heading">
              <div><h3>风险类型分布</h3><p>仅使用接口返回的风险类型聚合。</p></div>
            </div>
            <ElEmpty
              v-if="warnings.by_risk_type.length === 0"
              description="暂无风险类型分布"
            />
            <ElTable
              v-else
              :data="warnings.by_risk_type"
              row-key="risk_type"
              aria-label="风险类型分布"
            >
              <ElTableColumn
                label="风险类型"
                prop="risk_type"
                min-width="240"
              />
              <ElTableColumn
                label="次数"
                prop="count"
                width="140"
                align="right"
              />
            </ElTable>
          </section>
        </template>
      </section>
    </template>
  </section>
</template>
