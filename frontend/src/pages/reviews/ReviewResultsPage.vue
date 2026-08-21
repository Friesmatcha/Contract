<script setup lang="ts">
import {
  ArrowLeft,
  Document,
  Edit,
  Filter,
  ChatLineRound,
  Refresh,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { createReport } from '@/api/reports'
import {
  completeReviewTask,
  reviseClassification,
  reviseClauseComparison,
  reviseExtractedField,
  reviseRiskFinding,
} from '@/api/reviews'
import { createFeedback } from '@/api/feedback'
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
  ReportFormat,
  SourceLocator,
} from '@/api/types'
import PageState from '@/components/PageState.vue'
import { currentOrganizationMembership } from '@/features/auth/session'

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
const editTarget = ref<{ type: 'classification' | 'extracted_field' | 'risk_finding' | 'clause_comparison'; id: string; version: number } | null>(null)
const editStatus = ref('')
const editValue = ref('')
const editTitle = ref('')
const editDescription = ref('')
const editSuggestion = ref('')
const editDifferenceSummary = ref('')
const editReason = ref('')
const editError = ref('')
const editSaving = ref(false)
const completeSaving = ref(false)
const completeError = ref('')
const reportFormat = ref<ReportFormat>('html')
const reportCreating = ref(false)
const reportError = ref('')
const feedbackTarget = ref<{ type: 'classification' | 'extracted_field' | 'risk_finding' | 'clause_comparison'; id: string } | null>(null)
const feedbackLabel = ref<'correct' | 'incorrect' | 'modified' | 'ignored'>('correct')
const feedbackNote = ref('')
const feedbackCorrection = ref('')
const feedbackSaving = ref(false)
const feedbackError = ref('')
const sessionRevisions = ref<Array<{ type: string; id: string; revisionId?: string; version: number }>>([])

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
const canEdit = computed(() => task.value?.status === 'pending_review' && ['org_admin', 'reviewer'].includes(currentOrganizationMembership.value?.role ?? ''))
const canGenerateReport = computed(() => Boolean(
  task.value && ['pending_review', 'completed'].includes(task.value.status)
  && ['org_admin', 'reviewer'].includes(currentOrganizationMembership.value?.role ?? ''),
))
const completionBlockers = computed(() => results.value?.completion_blockers ?? [])

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

function openEdit(target: { type: 'classification' | 'extracted_field' | 'risk_finding' | 'clause_comparison'; id: string; version: number }): void {
  if (!results.value || !canEdit.value) return
  editTarget.value = target
  editError.value = ''
  editReason.value = ''
  editStatus.value = ''
  editValue.value = ''
  editTitle.value = ''
  editDescription.value = ''
  editSuggestion.value = ''
  editDifferenceSummary.value = ''
  if (target.type === 'classification') {
    editValue.value = results.value.classification.current_value
    editStatus.value = results.value.classification.status === 'detected' ? 'confirmed' : results.value.classification.status
  } else if (target.type === 'extracted_field') {
    const field = results.value.extracted_fields.find((item) => item.id === target.id)
    if (!field) return
    editValue.value = field.current_value === null ? 'null' : JSON.stringify(field.current_value, null, 2)
    editStatus.value = field.status === 'detected' ? 'confirmed' : field.status
  } else if (target.type === 'risk_finding') {
    const finding = results.value.risk_findings.find((item) => item.id === target.id)
    if (!finding) return
    editStatus.value = finding.status
    editTitle.value = finding.title
    editDescription.value = finding.description
    editSuggestion.value = finding.suggestion
  } else {
    const comparison = results.value.clause_comparisons.find((item) => item.id === target.id)
    if (!comparison) return
    editStatus.value = comparison.status
    editDifferenceSummary.value = comparison.difference_summary || ''
    editSuggestion.value = comparison.suggestion
  }
}

function closeEdit(): void {
  if (!editSaving.value) editTarget.value = null
}

function recordRevision(type: string, id: string, response: { revision_id?: string; version: number }): void {
  sessionRevisions.value.push({ type, id, revisionId: response.revision_id, version: response.version })
}

async function submitEdit(): Promise<void> {
  if (!editTarget.value || !results.value) return
  editSaving.value = true
  editError.value = ''
  try {
    const target = editTarget.value
    if (target.type === 'classification') {
      const response = await reviseClassification(target.id, {
        current_value: editValue.value as ContractCategory,
        status: editStatus.value as 'confirmed' | 'corrected' | 'needs_confirmation',
        reason: editReason.value || undefined,
        version: target.version,
      })
      recordRevision(target.type, target.id, response)
    } else if (target.type === 'extracted_field') {
      let value: unknown
      try { value = JSON.parse(editValue.value) } catch { throw new Error('字段值必须是合法 JSON。') }
      const response = await reviseExtractedField(target.id, {
        current_value: value,
        status: editStatus.value as 'not_found' | 'needs_confirmation' | 'confirmed' | 'corrected',
        reason: editReason.value || undefined,
        version: target.version,
      })
      recordRevision(target.type, target.id, response)
    } else if (target.type === 'risk_finding') {
      const response = await reviseRiskFinding(target.id, {
        status: editStatus.value as 'pending_review' | 'confirmed' | 'false_positive' | 'processed',
        title: editTitle.value,
        description: editDescription.value,
        suggestion: editSuggestion.value,
        reason: editReason.value || undefined,
        version: target.version,
      })
      recordRevision(target.type, target.id, response)
    } else {
      const response = await reviseClauseComparison(target.id, {
        status: editStatus.value as ClauseComparisonStatus,
        difference_summary: editDifferenceSummary.value,
        suggestion: editSuggestion.value,
        reason: editReason.value || undefined,
        version: target.version,
      })
      recordRevision(target.type, target.id, response)
    }
    editTarget.value = null
    await loadResults()
  } catch (error) {
    if (error instanceof ApiError && error.code === 'RESOURCE_VERSION_CONFLICT') {
      editError.value = '结果已被其他审核员更新，已刷新服务器版本。请重新打开编辑。'
      await load()
    } else {
      editError.value = error instanceof Error ? error.message : toSafeDisplayError(error).message
    }
  } finally {
    editSaving.value = false
  }
}

function openFeedback(type: 'classification' | 'extracted_field' | 'risk_finding' | 'clause_comparison', id: string): void {
  if (!canEdit.value) return
  feedbackTarget.value = { type, id }
  feedbackLabel.value = 'correct'
  feedbackNote.value = ''
  feedbackCorrection.value = ''
  feedbackError.value = ''
}

async function submitFeedback(): Promise<void> {
  if (!feedbackTarget.value) return
  feedbackSaving.value = true
  feedbackError.value = ''
  try {
    const body: Parameters<typeof createFeedback>[0] = {
      review_task_id: reviewTaskId.value,
      subject_type: feedbackTarget.value.type,
      subject_id: feedbackTarget.value.id,
      label: feedbackLabel.value,
      note: feedbackNote.value || undefined,
    }
    if (feedbackLabel.value === 'modified') {
      try { body.corrected_value = JSON.parse(feedbackCorrection.value) } catch { throw new Error('反馈修改值必须是合法 JSON。') }
    }
    await createFeedback(body, `feedback-${feedbackTarget.value.id}-${Date.now()}`)
    feedbackTarget.value = null
  } catch (error) {
    feedbackError.value = toSafeDisplayError(error).message
  } finally {
    feedbackSaving.value = false
  }
}

async function complete(): Promise<void> {
  if (!task.value || !canEdit.value) return
  completeSaving.value = true
  completeError.value = ''
  try {
    task.value = await completeReviewTask(task.value.id, undefined, `complete-${task.value.id}-${Date.now()}`)
    await loadResults()
  } catch (error) {
    completeError.value = toSafeDisplayError(error).message
    if (error instanceof ApiError && error.code === 'UNRESOLVED_REQUIRED_FINDINGS') await loadResults()
  } finally {
    completeSaving.value = false
  }
}

async function generateReport(): Promise<void> {
  if (!task.value || !canGenerateReport.value) return
  reportCreating.value = true
  reportError.value = ''
  try {
    const created = await createReport(
      task.value.id,
      reportFormat.value,
      `report-${task.value.id}-${reportFormat.value}-${Date.now()}`,
    )
    await router.push(`/reports/${created.id}`)
  } catch (error) {
    reportError.value = toSafeDisplayError(error).message
  } finally {
    reportCreating.value = false
  }
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
        <div class="review-result-heading-actions">
          <ElTag :type="workflowStatusType(task.status)">{{ taskStatusLabels[task.status] }}</ElTag>
          <div v-if="canGenerateReport" class="report-create-actions">
            <ElSelect v-model="reportFormat" aria-label="报告格式" class="report-format-select">
              <ElOption label="HTML 报告" value="html" />
              <ElOption label="PDF 报告" value="pdf" />
            </ElSelect>
            <ElButton :icon="Document" type="primary" :loading="reportCreating" @click="generateReport">生成报告</ElButton>
          </div>
          <ElButton v-if="canEdit" type="primary" :loading="completeSaving" @click="complete">完成审核</ElButton>
        </div>
      </div>

      <ElAlert
        v-if="reportError"
        title="报告未生成"
        :description="reportError"
        type="warning"
        :closable="false"
        show-icon
      />

      <ElAlert
        v-if="completeError"
        title="审核尚未完成"
        :description="completeError"
        type="warning"
        :closable="false"
        show-icon
      />

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
        <section v-if="completionBlockers.length > 0" class="summary-panel review-result-section review-blocker-panel">
          <div class="section-heading"><div><h2>完成审核前必须处理</h2><p>以下项目仍处于契约定义的人工阻塞状态。</p></div><ElTag type="warning">{{ completionBlockers.length }} 项</ElTag></div>
          <ul class="review-blocker-list">
            <li v-for="blocker in completionBlockers" :key="`${blocker.subject_type}-${blocker.subject_id}-${blocker.code}`">
              <span>{{ blocker.code }}</span><span class="technical-value">{{ blocker.subject_id }}</span><span>版本 {{ blocker.version }}</span>
            </li>
          </ul>
        </section>
        <section v-if="sessionRevisions.length > 0" class="summary-panel review-result-section">
          <div class="section-heading"><div><h2>本次会话修订</h2><p>完整修订历史没有独立读取接口，这里只显示本次会话收到的写入结果。</p></div></div>
          <ul class="review-session-revision-list"><li v-for="revision in sessionRevisions" :key="`${revision.id}-${revision.version}`"><span>{{ revision.type }}</span><span class="technical-value">{{ revision.id }}</span><span>版本 {{ revision.version }}</span></li></ul>
        </section>
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
          <div v-if="canEdit" class="result-action-row">
            <ElButton :icon="Edit" @click="openEdit({ type: 'classification', id: results.classification.id, version: results.classification.version })">编辑分类</ElButton>
            <ElButton :icon="ChatLineRound" @click="openFeedback('classification', results.classification.id)">提交反馈</ElButton>
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
              <div v-if="canEdit" class="result-action-row">
                <ElButton :icon="Edit" @click="openEdit({ type: 'extracted_field', id: field.id, version: field.version })">编辑字段</ElButton>
                <ElButton :icon="ChatLineRound" @click="openFeedback('extracted_field', field.id)">提交反馈</ElButton>
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
                  <td><div class="evidence-actions"><ElButton v-for="evidence in finding.evidence" :key="evidence.source_span_id" text :icon="View" :title="evidenceLocation(evidence)" @click="openEvidence(evidence)">{{ evidenceLocation(evidence) }}</ElButton><span v-if="finding.evidence.length === 0" class="muted-text">无定位</span><ElButton v-if="canEdit" :icon="Edit" @click="openEdit({ type: 'risk_finding', id: finding.id, version: finding.version })">编辑</ElButton><ElButton v-if="canEdit" :icon="ChatLineRound" @click="openFeedback('risk_finding', finding.id)">反馈</ElButton></div></td>
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
                  <td><div class="evidence-actions"><ElButton v-for="evidence in comparison.evidence" :key="evidence.source_span_id" text :icon="View" :title="evidenceLocation(evidence)" @click="openEvidence(evidence)">{{ evidenceLocation(evidence) }}</ElButton><span v-if="comparison.evidence.length === 0" class="muted-text">无定位</span><ElButton v-if="canEdit" :icon="Edit" @click="openEdit({ type: 'clause_comparison', id: comparison.id, version: comparison.version })">编辑</ElButton><ElButton v-if="canEdit" :icon="ChatLineRound" @click="openFeedback('clause_comparison', comparison.id)">反馈</ElButton></div></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
    <ElDialog
      :model-value="editTarget !== null"
      title="修订审核结果"
      width="560px"
      @close="closeEdit"
    >
      <ElAlert v-if="editError" title="修订未保存" :description="editError" type="warning" :closable="false" />
      <template v-if="editTarget">
        <ElForm label-position="top" class="review-edit-form">
          <ElFormItem label="状态">
            <ElSelect v-model="editStatus" aria-label="修订状态">
              <template v-if="editTarget.type === 'classification'"><ElOption label="已确认" value="confirmed" /><ElOption label="人工修订" value="corrected" /><ElOption label="待确认" value="needs_confirmation" /></template>
              <template v-else-if="editTarget.type === 'extracted_field'"><ElOption label="未发现" value="not_found" /><ElOption label="待确认" value="needs_confirmation" /><ElOption label="已确认" value="confirmed" /><ElOption label="人工修订" value="corrected" /></template>
              <template v-else-if="editTarget.type === 'risk_finding'"><ElOption label="待复核" value="pending_review" /><ElOption label="已确认" value="confirmed" /><ElOption label="误报" value="false_positive" /><ElOption label="已处理" value="processed" /></template>
              <template v-else><ElOption label="匹配" value="matched" /><ElOption label="存在偏差" value="deviated" /><ElOption label="缺失" value="missing" /><ElOption label="无法判断" value="uncertain" /></template>
            </ElSelect>
          </ElFormItem>
          <ElFormItem v-if="editTarget.type === 'classification'" label="当前分类"><ElSelect v-model="editValue" aria-label="当前分类"><ElOption v-for="(label, value) in categoryLabels" :key="value" :label="label" :value="value" /></ElSelect></ElFormItem>
          <ElFormItem v-else-if="editTarget.type === 'extracted_field'" label="当前字段值"><ElInput v-model="editValue" type="textarea" :rows="6" aria-label="当前字段值" /></ElFormItem>
          <template v-else-if="editTarget.type === 'risk_finding'">
            <ElFormItem label="标题"><ElInput v-model="editTitle" aria-label="风险标题" /></ElFormItem>
            <ElFormItem label="说明"><ElInput v-model="editDescription" type="textarea" :rows="3" aria-label="风险说明" /></ElFormItem>
            <ElFormItem label="建议"><ElInput v-model="editSuggestion" type="textarea" :rows="3" aria-label="风险建议" /></ElFormItem>
          </template>
          <template v-else>
            <ElFormItem label="差异摘要"><ElInput v-model="editDifferenceSummary" type="textarea" :rows="3" aria-label="差异摘要" /></ElFormItem>
            <ElFormItem label="建议"><ElInput v-model="editSuggestion" type="textarea" :rows="3" aria-label="条款建议" /></ElFormItem>
          </template>
          <ElFormItem label="修订原因"><ElInput v-model="editReason" type="textarea" :rows="2" aria-label="修订原因" /></ElFormItem>
        </ElForm>
      </template>
      <template #footer><ElButton @click="closeEdit">取消</ElButton><ElButton type="primary" :loading="editSaving" @click="submitEdit">保存修订</ElButton></template>
    </ElDialog>
    <ElDialog :model-value="feedbackTarget !== null" title="提交反馈" width="480px" @close="feedbackTarget = null">
      <ElAlert v-if="feedbackError" title="反馈未提交" :description="feedbackError" type="warning" :closable="false" />
      <ElForm label-position="top">
        <ElFormItem label="标注"><ElSelect v-model="feedbackLabel" aria-label="反馈标注"><ElOption label="正确" value="correct" /><ElOption label="错误" value="incorrect" /><ElOption label="修改" value="modified" /><ElOption label="忽略" value="ignored" /></ElSelect></ElFormItem>
        <ElFormItem v-if="feedbackLabel === 'modified'" label="人工结果"><ElInput v-model="feedbackCorrection" type="textarea" :rows="4" aria-label="人工结果" /></ElFormItem>
        <ElFormItem label="说明"><ElInput v-model="feedbackNote" type="textarea" :rows="3" aria-label="反馈说明" /></ElFormItem>
      </ElForm>
      <template #footer><ElButton @click="feedbackTarget = null">取消</ElButton><ElButton type="primary" :loading="feedbackSaving" @click="submitFeedback">提交反馈</ElButton></template>
    </ElDialog>
  </section>
</template>
