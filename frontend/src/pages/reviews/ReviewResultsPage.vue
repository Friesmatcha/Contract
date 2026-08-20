<script setup lang="ts">
import { ArrowLeft, Document, Refresh, View } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getReviewResults } from '@/api/reviews'
import { getReviewTask } from '@/api/reviews'
import type {
  ContractCategory,
  ExtractedFieldKey,
  ExtractedFieldResult,
  ResultStatus,
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
const loadingError = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const processing = ref(false)

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

const orderedFields = computed(() => {
  if (!results.value) return []
  const byKey = new Map(results.value.extracted_fields.map((field) => [field.field_key, field]))
  return fieldOrder.flatMap((key) => {
    const field = byKey.get(key)
    return field ? [field] : []
  })
})

function setLoadError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  loadingError.value = safe.message
  requestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(): Promise<void> {
  loading.value = true
  loadingError.value = ''
  forbidden.value = false
  processing.value = false
  try {
    task.value = await getReviewTask(reviewTaskId.value, false)
    try {
      results.value = await getReviewResults(reviewTaskId.value)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'RESULTS_NOT_READY') {
        processing.value = true
        results.value = null
      } else {
        throw error
      }
    }
  } catch (error) {
    setLoadError(error)
  } finally {
    loading.value = false
  }
}

function categoryLabel(value: ContractCategory): string {
  return categoryLabels[value]
}

function statusType(value: ResultStatus): 'success' | 'warning' | 'info' | 'primary' {
  if (value === 'detected' || value === 'confirmed') return 'success'
  if (value === 'needs_confirmation') return 'warning'
  if (value === 'corrected') return 'primary'
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

function openEvidence(evidence: SourceLocator): void {
  const query: Record<string, string> = { source_span_id: evidence.source_span_id }
  if (evidence.page_no !== null) query.page = String(evidence.page_no)
  void router.push({
    path: `/documents/${evidence.document_version_id}`,
    query,
  })
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
    <button
      class="back-link"
      type="button"
      @click="router.push(task ? `/reviews/${task.id}` : '/contracts')"
    >
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
      <div class="page-heading">
        <ElSkeleton
          :rows="2"
          animated
        />
      </div>
      <ElSkeleton
        :rows="12"
        animated
      />
    </template>
    <template v-else-if="task">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            {{ task.display_no }}
          </div>
          <h1>分类与字段抽取</h1>
          <p>审核结果来自 PostgreSQL 持久化事实，当前页面保持只读。</p>
        </div>
        <ElTag type="info">
          只读结果
        </ElTag>
      </div>

      <ElAlert
        v-if="processing"
        title="结果仍在处理中"
        description="分类或字段抽取尚未完成，完成后可在此查看证据。"
        type="info"
        :closable="false"
        show-icon
      >
        <template #default>
          <ElButton
            :icon="Refresh"
            @click="load"
          >
            重新检查
          </ElButton>
          <ElButton @click="router.push(`/reviews/${task.id}`)">
            查看进度
          </ElButton>
        </template>
      </ElAlert>

      <ElAlert
        v-if="loadingError && task && !processing"
        :title="loadingError"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <ElButton
            :icon="Refresh"
            @click="load"
          >
            重试
          </ElButton>
        </template>
      </ElAlert>

      <template v-if="results">
        <section class="summary-panel review-result-section">
          <div class="section-heading">
            <div>
              <h2>合同分类</h2>
              <p>分类值、置信度和原文证据。</p>
            </div>
            <ElTag :type="statusType(results.classification.status)">
              {{ statusLabels[results.classification.status] }}
            </ElTag>
          </div>
          <div class="review-classification-grid">
            <div>
              <span class="result-label">模型分类</span>
              <strong class="result-value">{{ categoryLabel(results.classification.model_value) }}</strong>
            </div>
            <div>
              <span class="result-label">当前分类</span>
              <strong class="result-value">{{ categoryLabel(results.classification.current_value) }}</strong>
            </div>
            <div>
              <span class="result-label">置信度</span>
              <strong class="result-value">{{ confidenceLabel(results.classification.confidence) }}</strong>
            </div>
          </div>
          <div class="evidence-list">
            <div
              v-for="evidence in results.classification.evidence"
              :key="evidence.source_span_id"
              class="evidence-row"
            >
              <blockquote>{{ evidence.quote }}</blockquote>
              <ElButton
                text
                :icon="View"
                @click="openEvidence(evidence)"
              >
                查看证据位置
              </ElButton>
            </div>
            <ElEmpty
              v-if="results.classification.evidence.length === 0"
              description="暂无证据定位"
            />
          </div>
        </section>

        <section class="table-panel review-result-section">
          <div class="section-heading review-result-table-heading">
            <div>
              <h2>核心字段</h2>
              <p>缺失字段仍保留明确状态，不伪造证据。</p>
            </div>
            <ElIcon><Document /></ElIcon>
          </div>
          <div class="review-field-grid">
            <article
              v-for="field in orderedFields"
              :key="field.id"
              class="review-field-card"
            >
              <div class="review-field-card-heading">
                <div>
                  <h3>{{ fieldLabels[field.field_key] }}</h3>
                  <span class="technical-value">{{ field.field_key }}</span>
                </div>
                <ElTag
                  size="small"
                  :type="statusType(field.status)"
                >
                  {{ fieldStatus(field) }}
                </ElTag>
              </div>
              <dl class="review-field-values">
                <div>
                  <dt>模型值</dt>
                  <dd><pre>{{ formatValue(field.model_value) }}</pre></dd>
                </div>
                <div>
                  <dt>当前值</dt>
                  <dd><pre>{{ formatValue(field.current_value) }}</pre></dd>
                </div>
                <div class="review-field-confidence">
                  <dt>置信度</dt>
                  <dd>{{ confidenceLabel(field.confidence) }}</dd>
                </div>
              </dl>
              <div class="evidence-list compact-evidence-list">
                <div
                  v-for="evidence in field.evidence"
                  :key="evidence.source_span_id"
                  class="evidence-row"
                >
                  <blockquote>{{ evidence.quote }}</blockquote>
                  <ElButton
                    text
                    :icon="View"
                    @click="openEvidence(evidence)"
                  >
                    查看位置
                  </ElButton>
                </div>
                <span
                  v-if="field.evidence.length === 0"
                  class="muted-text"
                >无证据定位</span>
              </div>
            </article>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>
