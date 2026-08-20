<script setup lang="ts">
import {
  ArrowLeft,
  Document,
  Filter,
  Refresh,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getReviewResults, getReviewTask } from '@/api/reviews'
import type {
  ClauseComparisonStatus,
  ContractCategory,
  ExtractedFieldKey,
  ExtractedFieldResult,
  ResultStatus,
  RiskFindingStatus,
  RiskSeverity,
  ReviewResults,
  ReviewTask,
  SourceLocator,
} from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const router = useRouter()
const reviewTaskId = computed(() => String(route.params.reviewTaskId ?? ''))

const task = ref<ReviewTask | null>(null)
const results = ref<ReviewResults | null>(null)
const loading = ref(true)
const resultsLoading = ref(false)
const loadingError = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const processing = ref(false)

const riskSeverity = ref<RiskSeverity | ''>('')
const riskStatus = ref<RiskFindingStatus | ''>('')
const clauseStatus = ref<ClauseComparisonStatus | ''>('')

const fieldOrder: ExtractedFieldKey[] = [
  'parties',
  'signing_date',
  'contract_amount',
  'performance_period',
  'dispute_resolution',
  'payment_terms',
  'auto_renewal',
]
const fieldLabels: Record<ExtractedFieldKey, string> = {
  parties: '合同主体',
  signing_date: '签署日期',
  contract_amount: '合同金额',
  performance_period: '履行期限',
  dispute_resolution: '争议解决',
  payment_terms: '付款条件',
  auto_renewal: '自动续期',
}
const categoryLabels: Record<ContractCategory, string> = {
  purchase: '采购合同',
  sales: '销售合同',
  nda: '保密协议',
  outsourcing: '服务外包',
  employment: '劳动合同',
  other: '其他合同',
}
const statusLabels: Record<ResultStatus, string> = {
  detected: '已识别',
  not_found: '未发现',
  needs_confirmation: '待确认',
  confirmed: '已确认',
  corrected: '人工修订',
}
const riskStatusLabels: Record<RiskFindingStatus, string> = {
  pending_review: '待复核',
  confirmed: '已确认',
  false_positive: '误报',
  processed: '已处理',
}
const clauseStatusLabels: Record<ClauseComparisonStatus, string> = {
  matched: '匹配',
  deviated: '存在偏差',
  missing: '缺失',
  uncertain: '无法判断',
}
const severityLabels: Record<RiskSeverity, string> = {
  high: '高',
  medium: '中',
  low: '低',
}
const taskStatusLabels: Record<ReviewTask['status'], string> = {
  pending: '等待处理',
  parsing: '正在解析',
  reviewing: '正在审核',
  pending_review: '等待人工复核',
  completed: '审核已完成',
  failed: '审核失败',
  archived: '历史审核任务',
}

const orderedFields = computed(() => {
  if (!results.value) return []
  const byKey = new Map(results.value.extracted_fields.map((field) => [field.field_key, field]))
  return fieldOrder.flatMap((key) => {
    const field = byKey.get(key)
    return field ? [field] : []
  })
})

const hasFilters = computed(() => Boolean(riskSeverity.value || riskStatus.value || clauseStatus.value))
const resultReadyStatuses = new Set<ReviewTask['status']>(['pending_review', 'completed', 'archived'])

function setLoadError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  loadingError.value = safe.message
  requestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

function resultQuery() {
  return {
    includeEvidence: true,
    riskSeverity: riskSeverity.value || undefined,
    riskStatus: riskStatus.value || undefined,
    clauseStatus: clauseStatus.value || undefined,
  }
}

async function loadResults(): Promise<void> {
  if (task.value && !resultReadyStatuses.has(task.value.status) && task.value.status !== 'failed') {
    processing.value = true
    results.value = null
    return
  }
  resultsLoading.value = true
  loadingError.value = ''
  forbidden.value = false
  processing.value = false
  try {
    results.value = await getReviewResults(reviewTaskId.value, resultQuery())
  } catch (error) {
    if (error instanceof ApiError && error.code === 'RESULTS_NOT_READY') {
      processing.value = task.value?.status !== 'failed'
      results.value = null
    } else {
      setLoadError(error)
    }
  } finally {
    resultsLoading.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  loadingError.value = ''
  forbidden.value = false
  try {
    task.value = await getReviewTask(reviewTaskId.value, false)
    if (resultReadyStatuses.has(task.value.status) || task.value.status === 'failed') {
      await loadResults()
    } else {
      processing.value = true
      results.value = null
    }
  } catch (error) {
    setLoadError(error)
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  riskSeverity.value = ''
  riskStatus.value = ''
  clauseStatus.value = ''
  void loadResults()
}

function categoryLabel(value: ContractCategory): string {
  return categoryLabels[value]
}

function resultStatusType(value: ResultStatus): 'success' | 'warning' | 'info' | 'primary' {
  if (value === 'detected' || value === 'confirmed') return 'success'
  if (value === 'needs_confirmation') return 'warning'
  if (value === 'corrected') return 'primary'
  return 'info'
}

function workflowStatusType(value: ReviewTask['status']): 'success' | 'warning' | 'info' | 'danger' {
  if (value === 'completed') return 'success'
  if (value === 'failed') return 'danger'
  if (value === 'pending_review') return 'warning'
  return 'info'
}

function severityType(value: RiskSeverity): 'danger' | 'warning' | 'info' {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  return 'info'
}

function riskStatusType(value: RiskFindingStatus): 'success' | 'warning' | 'info' | 'danger' {
  if (value === 'confirmed' || value === 'processed') return 'success'
  if (value === 'false_positive') return 'info'
  return 'warning'
}

function clauseStatusType(value: ClauseComparisonStatus): 'success' | 'warning' | 'info' | 'danger' {
  if (value === 'matched') return 'success'
  if (value === 'deviated') return 'warning'
  if (value === 'missing') return 'danger'
  return 'info'
}

function formatValue(value: unknown | null): string {
  if (value === null || value === undefined) return '未发现'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function confidenceLabel(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

function evidenceLocation(evidence: SourceLocator): string {
  if (evidence.page_no !== null) return `第 ${evidence.page_no} 页`
  if (evidence.paragraph_no !== null) return `第 ${evidence.paragraph_no} 段`
  return '原文定位'
}

function openEvidence(evidence: SourceLocator): void {
  const query: Record<string, string> = { source_span_id: evidence.source_span_id }
  if (evidence.page_no !== null) query.page = String(evidence.page_no)
  void router.push({ path: `/documents/${evidence.document_version_id}`, query })
}

function fieldStatus(field: ExtractedFieldResult): string {
  return statusLabels[field.status]
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="admin-page review-results-page">
    <button class="back-link" type="button" @click="router.push(task ? `/reviews/${task.id}` : '/contracts')">
      <ElIcon><ArrowLeft /></ElIcon> 返回审核进度
    </button>

    <PageState
      v-if="forbidden"
      title="无法访问审核结果"
      :description="loadingError || '结果不存在或当前账户没有查看权限。'"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <PageState
      v-else-if="loadingError && !task"
      title="审核结果加载失败"
      :description="loadingError"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <template v-else-if="loading && !task">
      <div class="page-heading"><ElSkeleton :rows="2" animated /></div>
      <ElSkeleton :rows="16" animated />
    </template>
    <template v-else-if="task">
      <div class="page-heading review-results-heading">
        <div>
          <div class="technical-value">{{ task.display_no }}</div>
          <h1>审核结果与人工复核</h1>
          <p>分类、字段、风险和条款结果均来自当前审核任务的持久化版本。</p>
        </div>
        <ElTag :type="workflowStatusType(task.status)">{{ taskStatusLabels[task.status] }}</ElTag>
      </div>

      <ElAlert
        v-if="task.status === 'failed'"
        title="审核任务执行失败"
        :description="task.error_message || '审核阶段执行失败，请返回进度页查看可重试状态。'"
        type="error"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="review-result-alert-actions">
            <ElIcon><WarningFilled /></ElIcon>
            <span v-if="task.error_code">错误代码：{{ task.error_code }}</span>
            <ElButton :icon="Refresh" @click="router.push(`/reviews/${task.id}`)">查看进度</ElButton>
          </div>
        </template>
      </ElAlert>

      <ElAlert
        v-else-if="processing"
        title="结果仍在处理中"
        description="审核阶段尚未全部完成，完成后可在此查看风险、条款和证据。"
        type="info"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="review-result-alert-actions">
            <ElButton :icon="Refresh" @click="load">重新检查</ElButton>
            <ElButton @click="router.push(`/reviews/${task.id}`)">查看进度</ElButton>
          </div>
        </template>
      </ElAlert>

      <ElAlert
        v-if="loadingError && !processing && task.status !== 'failed'"
        title="结果加载失败"
        :description="loadingError"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default><ElButton :icon="Refresh" @click="loadResults">重试</ElButton></template>
      </ElAlert>

      <template v-if="results">
        <section class="summary-panel review-result-section review-summary-panel">
          <div class="section-heading">
            <div><h2>结果摘要</h2><p>风险统计和待处理数量随当前筛选条件更新。</p></div>
            <ElIcon><Document /></ElIcon>
          </div>
          <div class="review-summary-grid">
            <div><span class="result-label">风险总数</span><strong>{{ results.summary.risk_total }}</strong></div>
            <div class="review-summary-critical"><span class="result-label">高风险</span><strong>{{ results.summary.high }}</strong></div>
            <div class="review-summary-warning"><span class="result-label">中风险</span><strong>{{ results.summary.medium }}</strong></div>
            <div><span class="result-label">低风险</span><strong>{{ results.summary.low }}</strong></div>
            <div><span class="result-label">预警</span><strong>{{ results.summary.warning_total }}</strong></div>
            <div class="review-summary-unresolved"><span class="result-label">待处理</span><strong>{{ results.summary.unresolved_count }}</strong></div>
          </div>
        </section>

        <section class="filter-panel review-results-filter" aria-label="结果筛选">
          <div class="review-filter-label"><ElIcon><Filter /></ElIcon><span>筛选结果</span></div>
          <ElSelect v-model="riskSeverity" clearable placeholder="风险严重度" aria-label="风险严重度">
            <ElOption v-for="value in ['high', 'medium', 'low']" :key="value" :label="severityLabels[value as RiskSeverity]" :value="value" />
          </ElSelect>
          <ElSelect v-model="riskStatus" clearable placeholder="风险状态" aria-label="风险状态">
            <ElOption v-for="value in ['pending_review', 'confirmed', 'false_positive', 'processed']" :key="value" :label="riskStatusLabels[value as RiskFindingStatus]" :value="value" />
          </ElSelect>
          <ElSelect v-model="clauseStatus" clearable placeholder="条款状态" aria-label="条款状态">
            <ElOption v-for="value in ['matched', 'deviated', 'missing', 'uncertain']" :key="value" :label="clauseStatusLabels[value as ClauseComparisonStatus]" :value="value" />
          </ElSelect>
          <ElButton type="primary" :loading="resultsLoading" @click="loadResults">应用筛选</ElButton>
          <ElButton :disabled="!hasFilters || resultsLoading" @click="resetFilters">清除</ElButton>
        </section>

        <section class="summary-panel review-result-section">
          <div class="section-heading">
            <div><h2>合同分类</h2><p>分类值、置信度和原文证据。</p></div>
            <ElTag :type="resultStatusType(results.classification.status)">{{ statusLabels[results.classification.status] }}</ElTag>
          </div>
          <div class="review-classification-grid">
            <div><span class="result-label">模型分类</span><strong class="result-value">{{ categoryLabel(results.classification.model_value) }}</strong></div>
            <div><span class="result-label">当前分类</span><strong class="result-value">{{ categoryLabel(results.classification.current_value) }}</strong></div>
            <div><span class="result-label">置信度</span><strong class="result-value">{{ confidenceLabel(results.classification.confidence) }}</strong></div>
          </div>
          <div class="evidence-list">
            <div v-for="evidence in results.classification.evidence" :key="evidence.source_span_id" class="evidence-row">
              <blockquote>{{ evidence.quote }}</blockquote>
              <ElButton text :icon="View" @click="openEvidence(evidence)">查看证据位置</ElButton>
            </div>
            <ElEmpty v-if="results.classification.evidence.length === 0" description="暂无证据定位" />
          </div>
        </section>

        <section class="table-panel review-result-section">
          <div class="section-heading review-result-table-heading">
            <div><h2>核心字段</h2><p>缺失字段保留 JSON null 和明确状态。</p></div>
            <ElIcon><Document /></ElIcon>
          </div>
          <div class="review-field-grid">
            <article v-for="field in orderedFields" :key="field.id" class="review-field-card">
              <div class="review-field-card-heading">
                <div><h3>{{ fieldLabels[field.field_key] }}</h3><span class="technical-value">{{ field.field_key }}</span></div>
                <ElTag size="small" :type="resultStatusType(field.status)">{{ fieldStatus(field) }}</ElTag>
              </div>
              <dl class="review-field-values">
                <div><dt>模型值</dt><dd><pre>{{ formatValue(field.model_value) }}</pre></dd></div>
                <div><dt>当前值</dt><dd><pre>{{ formatValue(field.current_value) }}</pre></dd></div>
                <div class="review-field-confidence"><dt>置信度</dt><dd>{{ confidenceLabel(field.confidence) }}</dd></div>
              </dl>
              <div class="evidence-list compact-evidence-list">
                <div v-for="evidence in field.evidence" :key="evidence.source_span_id" class="evidence-row">
                  <blockquote>{{ evidence.quote }}</blockquote>
                  <ElButton text :icon="View" @click="openEvidence(evidence)">查看位置</ElButton>
                </div>
                <span v-if="field.evidence.length === 0" class="muted-text">无证据定位</span>
              </div>
            </article>
          </div>
        </section>

        <section class="table-panel review-result-section review-results-table-panel" aria-labelledby="risk-findings-title">
          <div class="section-heading review-result-table-heading">
            <div><h2 id="risk-findings-title">风险发现</h2><p>风险来源、严重度、处置状态和原文依据。</p></div>
            <ElTag type="danger">{{ results.risk_findings.length }} 条</ElTag>
          </div>
          <ElEmpty v-if="results.risk_findings.length === 0" :description="hasFilters ? '当前筛选无风险发现' : '暂无风险发现'" />
          <div v-else class="review-result-table-scroll">
            <table class="review-result-table">
              <thead><tr><th>严重度</th><th>风险类型</th><th>标题与依据</th><th>建议</th><th>来源 / 状态</th><th>置信度</th><th>证据</th></tr></thead>
              <tbody>
                <tr v-for="finding in results.risk_findings" :key="finding.id">
                  <td><ElTag :type="severityType(finding.severity)">{{ severityLabels[finding.severity] }}</ElTag></td>
                  <td><span class="technical-value">{{ finding.risk_type }}</span></td>
                  <td><strong>{{ finding.title }}</strong><p class="result-table-copy">{{ finding.description }}</p><p class="result-table-basis">依据：{{ finding.basis }}</p></td>
                  <td class="result-table-copy">{{ finding.suggestion }}</td>
                  <td><ElTag size="small" type="info">{{ finding.source === 'rule' ? '规则' : '模型' }}</ElTag><ElTag size="small" :type="riskStatusType(finding.status)">{{ riskStatusLabels[finding.status] }}</ElTag></td>
                  <td>{{ confidenceLabel(finding.confidence) }}</td>
                  <td><div class="evidence-actions"><ElButton v-for="evidence in finding.evidence" :key="evidence.source_span_id" text :icon="View" :title="evidenceLocation(evidence)" @click="openEvidence(evidence)">{{ evidenceLocation(evidence) }}</ElButton><span v-if="finding.evidence.length === 0" class="muted-text">无定位</span></div></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="table-panel review-result-section review-results-table-panel" aria-labelledby="clause-comparisons-title">
          <div class="section-heading review-result-table-heading">
            <div><h2 id="clause-comparisons-title">条款对照</h2><p>标准条款与合同原文的匹配、偏差和缺失状态。</p></div>
            <ElTag type="info">{{ results.clause_comparisons.length }} 条</ElTag>
          </div>
          <ElEmpty v-if="results.clause_comparisons.length === 0" :description="hasFilters ? '当前筛选无条款结果' : '暂无条款比对结果'" />
          <div v-else class="review-result-table-scroll">
            <table class="review-result-table clause-result-table">
              <thead><tr><th>条款</th><th>合同原文</th><th>差异摘要</th><th>严重度</th><th>状态</th><th>建议</th><th>证据</th></tr></thead>
              <tbody>
                <tr v-for="comparison in results.clause_comparisons" :key="comparison.id">
                  <td><span class="technical-value">{{ comparison.clause_key }}</span></td>
                  <td class="result-table-copy">{{ comparison.contract_text || '未发现合同原文' }}</td>
                  <td class="result-table-copy">{{ comparison.difference_summary || '无差异说明' }}</td>
                  <td><ElTag :type="severityType(comparison.severity)">{{ severityLabels[comparison.severity] }}</ElTag></td>
                  <td><ElTag :type="clauseStatusType(comparison.status)">{{ clauseStatusLabels[comparison.status] }}</ElTag></td>
                  <td class="result-table-copy">{{ comparison.suggestion }}</td>
                  <td><div class="evidence-actions"><ElButton v-for="evidence in comparison.evidence" :key="evidence.source_span_id" text :icon="View" :title="evidenceLocation(evidence)" @click="openEvidence(evidence)">{{ evidenceLocation(evidence) }}</ElButton><span v-if="comparison.evidence.length === 0" class="muted-text">无定位</span></div></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>
