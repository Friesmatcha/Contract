<script setup lang="ts">
import { ArrowLeft, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { toSafeDisplayError } from '@/api/client'
import { getContract } from '@/api/contracts'
import { getReviewTask, retryReviewTask } from '@/api/reviews'
import type { ReviewStage, ReviewStageRun, ReviewStatus, ReviewTask } from '@/api/types'
import PageState from '@/components/PageState.vue'
import {
  currentOrganizationId,
  currentOrganizationMembership,
} from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => String(route.params.reviewTaskId ?? ''))
const organizationId = currentOrganizationId
const role = computed(() => currentOrganizationMembership.value?.role)
const canRetry = computed(() => role.value === 'org_admin' || role.value === 'reviewer')

const task = ref<ReviewTask | null>(null)
const contractTitle = ref('')
const loading = ref(true)
const loadingError = ref('')
const requestId = ref<string>()
const networkError = ref('')
const retryError = ref('')
const retrying = ref(false)
const nextDelay = ref(2000)
let timer: ReturnType<typeof setTimeout> | undefined

const settledStatuses: ReviewStatus[] = ['pending_review', 'completed', 'failed', 'archived']
const stageNames: Record<'queued' | ReviewStage, string> = {
  queued: '等待处理',
  parsing: '文档解析',
  classification: '分类阶段',
  extraction: '字段抽取',
  risk_analysis: '风险分析',
  clause_comparison: '条款比对',
  report: '审核报告阶段',
}
const statusNames: Record<ReviewStatus, string> = {
  pending: '等待处理',
  parsing: '正在解析合同',
  reviewing: '正在执行审核',
  pending_review: '等待人工复核',
  completed: '审核已完成',
  failed: '审核失败',
  archived: '历史审核任务',
}

const isSettled = computed(() => Boolean(task.value && settledStatuses.includes(task.value.status)))
const statusType = computed(() => {
  switch (task.value?.status) {
    case 'completed': return 'success'
    case 'failed': return 'danger'
    case 'pending_review': return 'warning'
    case 'archived': return 'info'
    default: return 'primary'
  }
})

function clearTimer(): void {
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
}

function formatDate(value: string | null): string {
  if (!value) return '未记录'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function setLoadError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  loadingError.value = safe.message
  requestId.value = safe.requestId
}

function schedulePoll(delay = nextDelay.value): void {
  clearTimer()
  if (isSettled.value) return
  const pollingDelay = document.hidden
    ? Math.min(60000, Math.max(10000, delay * 2))
    : delay
  timer = setTimeout(() => {
    void load(true)
  }, pollingDelay)
}

async function load(background = false): Promise<void> {
  if (!background) {
    loading.value = true
    loadingError.value = ''
  }
  networkError.value = ''
  try {
    const latest = await getReviewTask(taskId.value, true)
    task.value = latest
    const scheduledDelay = nextDelay.value
    if (latest.status === 'pending' || latest.status === 'parsing' || latest.status === 'reviewing') {
      nextDelay.value = Math.min(30000, Math.max(2000, scheduledDelay * 2))
    }
    if (!contractTitle.value) {
      try {
        const contract = await getContract(latest.contract_id, organizationId.value)
        contractTitle.value = contract.title
      } catch {
        contractTitle.value = '合同'
      }
    }
    schedulePoll(scheduledDelay)
  } catch (error) {
    if (background && task.value) {
      networkError.value = toSafeDisplayError(error).message
      clearTimer()
    } else {
      setLoadError(error)
    }
  } finally {
    loading.value = false
  }
}

async function retry(): Promise<void> {
  if (!task.value || !canRetry.value || retrying.value) return
  retrying.value = true
  retryError.value = ''
  try {
    nextDelay.value = 2000
    await retryReviewTask(task.value.id, {}, crypto.randomUUID())
    await load()
  } catch (error) {
    retryError.value = toSafeDisplayError(error).message
  } finally {
    retrying.value = false
  }
}

function onVisibilityChange(): void {
  clearTimer()
  if (!document.hidden) {
    void load(true)
  } else if (!isSettled.value) {
    schedulePoll()
  }
}

function stageType(run: ReviewStageRun): 'success' | 'danger' | 'warning' | 'info' {
  if (run.status === 'succeeded') return 'success'
  if (run.status === 'failed') return 'danger'
  if (run.status === 'running') return 'warning'
  return 'info'
}

function stageStatusLabel(value: ReviewStageRun['status']): string {
  return {
    pending: '等待',
    running: '执行中',
    succeeded: '完成',
    failed: '失败',
    retryable: '可重试',
  }[value]
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  void load()
})

onBeforeUnmount(() => {
  clearTimer()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <section class="admin-page review-progress-page">
    <button
      class="back-link"
      type="button"
      @click="router.push(task ? `/contracts/${task.contract_id}` : '/contracts')"
    >
      <ElIcon><ArrowLeft /></ElIcon> 返回合同详情
    </button>
    <PageState
      v-if="loadingError && !task"
      title="审核任务无法加载"
      :description="loadingError"
      icon="error"
      :request-id="requestId"
      @retry="load()"
    />
    <template v-else-if="loading && !task">
      <div class="page-heading">
        <ElSkeleton
          :rows="2"
          animated
        />
      </div>
      <ElSkeleton
        :rows="10"
        animated
      />
    </template>
    <template v-else-if="task">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            {{ task.display_no }}
          </div>
          <h1>{{ statusNames[task.status] }}</h1>
          <p>{{ contractTitle || '合同审核任务' }}</p>
        </div>
        <ElTag :type="statusType">
          {{ statusNames[task.status] }}
        </ElTag>
      </div>

      <ElAlert
        v-if="networkError"
        title="暂时无法更新审核状态"
        :description="networkError"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <ElButton
            :icon="Refresh"
            @click="load()"
          >
            重新连接
          </ElButton>
        </template>
      </ElAlert>
      <ElAlert
        v-if="retryError"
        :title="retryError"
        type="error"
        :closable="false"
        show-icon
      />

      <div class="review-progress-layout">
        <section class="summary-panel review-progress-summary">
          <div class="section-heading">
            <div><h2>审核进度</h2><p>进度和阶段均来自服务端任务事实。</p></div>
            <ElButton
              text
              :icon="Refresh"
              aria-label="刷新审核状态"
              title="刷新审核状态"
              @click="load()"
            />
          </div>
          <ElProgress
            :percentage="task.progress"
            :status="task.status === 'failed' ? 'exception' : task.status === 'completed' ? 'success' : undefined"
            :stroke-width="12"
          />
          <div class="review-progress-number">
            {{ task.progress }}%
          </div>
          <dl class="metadata-list metadata-list-single">
            <div><dt>当前阶段</dt><dd>{{ stageNames[task.current_stage] }}</dd></div>
            <div><dt>开始时间</dt><dd>{{ formatDate(task.started_at) }}</dd></div>
            <div><dt>结束时间</dt><dd>{{ formatDate(task.finished_at) }}</dd></div>
            <div>
              <dt>输入文件版本</dt><dd class="technical-value">
                {{ task.contract_file_id }}
              </dd>
            </div>
          </dl>
        </section>

        <section class="summary-panel">
          <div class="section-heading">
            <div><h2>阶段记录</h2><p>每个阶段保留尝试次数和安全错误信息。</p></div>
          </div>
          <ElTimeline v-if="task.stage_runs?.length">
            <ElTimelineItem
              v-for="run in task.stage_runs"
              :key="run.id"
              :type="stageType(run)"
              :timestamp="formatDate(run.finished_at || run.started_at)"
            >
              <div class="review-stage-row">
                <strong>{{ stageNames[run.stage] }}</strong>
                <ElTag
                  size="small"
                  :type="stageType(run)"
                >
                  {{ stageStatusLabel(run.status) }}
                </ElTag>
              </div>
              <p>第 {{ run.attempt_no }} 次尝试</p>
              <p
                v-if="run.error_message"
                class="review-error-copy"
              >
                {{ run.error_message }}
              </p>
            </ElTimelineItem>
          </ElTimeline>
          <ElEmpty
            v-else
            description="暂无阶段记录"
          />
        </section>
      </div>

      <ElAlert
        v-if="task.status === 'failed'"
        class="review-failure-alert"
        :title="task.error_message || '审核阶段执行失败。'"
        :description="task.error_code ? `错误代码：${task.error_code}` : undefined"
        type="error"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="review-failure-actions">
            <ElIcon><WarningFilled /></ElIcon>
            <ElButton
              v-if="canRetry"
              type="primary"
              :loading="retrying"
              @click="retry"
            >
              重试失败阶段
            </ElButton>
            <span v-else>当前账户仅可查看失败详情。</span>
          </div>
        </template>
      </ElAlert>

      <div
        v-if="task.status === 'pending_review' || task.status === 'completed'"
        class="page-heading-actions review-actions"
      >
        <ElButton
          type="primary"
          disabled
        >
          进入审核结果
        </ElButton>
        <span class="form-note">结果与人工复核属于后续 Phase。</span>
      </div>
      <div
        v-else-if="isSettled"
        class="page-heading-actions review-actions"
      >
        <ElButton @click="router.push(`/contracts/${task.contract_id}`)">
          返回合同
        </ElButton>
      </div>
    </template>
  </section>
</template>
