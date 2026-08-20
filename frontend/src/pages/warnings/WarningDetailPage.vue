<script setup lang="ts">
import { ArrowLeft, CircleCheck, Close, EditPen, Refresh, User } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { createWarningEvent, getWarning } from '@/api/warnings'
import type { WarningDetail, WarningEventRequest, WarningEventType, WarningSeverity, WarningStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { currentOrganizationId, currentOrganizationMembership } from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const organizationId = currentOrganizationId
const warningId = computed(() => String(route.params.warningId ?? ''))
const warning = ref<WarningDetail | null>(null)
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const actionOpen = ref(false)
const actionType = ref<WarningEventType>('note')
const note = ref('')
const assigneeId = ref('')
const dueAt = ref('')
const resolution = ref('')

const role = computed(() => currentOrganizationMembership.value?.role)
const canWrite = computed(() => role.value === 'org_admin' || role.value === 'reviewer')
const canReopen = computed(() => role.value === 'org_admin' && (warning.value?.status === 'ignored' || warning.value?.status === 'closed'))
const statusLabels: Record<WarningStatus, string> = {
  pending_confirmation: '待确认', in_progress: '处理中', ignored: '已忽略', resolved: '已解决', closed: '已关闭',
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

async function load(): Promise<void> {
  if (!organizationId.value || !warningId.value) return
  loading.value = true
  resetError()
  try {
    warning.value = await getWarning(warningId.value, organizationId.value)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    loading.value = false
  }
}

function openAction(type: WarningEventType): void {
  actionType.value = type
  note.value = ''
  resolution.value = ''
  assigneeId.value = warning.value?.assignee_id ?? ''
  dueAt.value = warning.value?.due_at ? warning.value.due_at.slice(0, 16) : ''
  actionOpen.value = true
}

async function confirmAction(type: 'false_positive' | 'ignore' | 'close' | 'reopen'): Promise<void> {
  const labels: Record<typeof type, string> = { false_positive: '标记误报', ignore: '忽略预警', close: '关闭预警', reopen: '重新打开' }
  try {
    await ElMessageBox.confirm(`确定${labels[type]}吗？该操作会追加到预警时间线。`, '确认操作', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: type === 'close' ? 'warning' : 'info',
    })
    await submit(type)
  } catch {
    // Cancelled confirmation is intentionally silent.
  }
}

async function submit(type = actionType.value): Promise<void> {
  if (!organizationId.value || !warning.value || submitting.value) return
  const body: WarningEventRequest = { type }
  if (type === 'assign') {
    body.assignee_id = assigneeId.value || undefined
    body.due_at = dueAt.value ? new Date(dueAt.value).toISOString() : null
    body.note = note.value.trim() || undefined
  } else if (type === 'note') {
    body.note = note.value.trim()
  } else if (type === 'close') {
    body.resolution = resolution.value.trim() || undefined
  }
  if ((type === 'note' && !body.note) || (type === 'assign' && !body.assignee_id) || (type === 'close' && !body.resolution)) {
    errorMessage.value = type === 'assign' ? '请选择责任人。' : type === 'close' ? '请输入关闭结论。' : '说明不能为空。'
    return
  }
  submitting.value = true
  resetError()
  try {
    await createWarningEvent(warning.value.id, organizationId.value, body)
    actionOpen.value = false
    await load()
    ElMessage.success('预警事件已记录。')
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
    if (error instanceof ApiError && error.code === 'INVALID_STATE_TRANSITION') await load()
  } finally {
    submitting.value = false
  }
}

function openEvidence(evidence: WarningDetail['evidence'][number]): void {
  void router.push({ path: `/documents/${evidence.document_version_id}`, query: { source_span_id: evidence.source_span_id } })
}

function eventLabel(eventType: string): string {
  return {
    created: '系统触发', confirm: '确认预警', false_positive: '标记误报', ignore: '忽略预警', assign: '分派责任人',
    note: '添加说明', resolve: '解决预警', close: '关闭预警', reopen: '重新打开',
  }[eventType] ?? eventType
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page warning-detail-page">
    <button
      class="back-link"
      type="button"
      @click="router.push('/warnings')"
    >
      <ElIcon><ArrowLeft /></ElIcon>返回预警中心
    </button>
    <PageState
      v-if="forbidden"
      title="无法访问预警"
      :description="errorMessage || '预警不存在或当前账户没有查看权限。'"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <PageState
      v-else-if="errorMessage && !warning"
      title="预警加载失败"
      :description="errorMessage"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <template v-else-if="warning">
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />
      <header class="warning-detail-header">
        <div>
          <div class="warning-detail-title-row">
            <h1>预警详情</h1>
            <ElTag :type="severityType(warning.severity)">
              {{ severityLabels[warning.severity] }}
            </ElTag>
            <ElTag :type="statusType(warning.status)">
              {{ statusLabels[warning.status] }}
            </ElTag>
          </div>
          <p class="muted-copy">
            {{ warning.trigger_type }} · 触发于 {{ formatDate(warning.triggered_at) }}
          </p>
        </div>
        <ElButton
          :icon="Refresh"
          :loading="loading"
          @click="load"
        >
          刷新
        </ElButton>
      </header>
      <section class="warning-context-grid">
        <div><span>预警 ID</span><strong class="technical-value">{{ warning.id.slice(0, 12) }}</strong></div>
        <div>
          <span>相关合同</span><button
            class="table-link"
            type="button"
            @click="router.push(`/contracts/${warning.contract_id}`)"
          >
            {{ warning.contract_id.slice(0, 12) }}
          </button>
        </div>
        <div>
          <span>相关审核</span><button
            class="table-link"
            type="button"
            @click="router.push(`/reviews/${warning.review_task_id}/results`)"
          >
            {{ warning.review_task_id.slice(0, 12) }}
          </button>
        </div>
        <div><span>责任人</span><strong>{{ warning.assignee?.display_name || warning.assignee?.email || '未分派' }}</strong></div>
        <div><span>截止时间</span><strong>{{ formatDate(warning.due_at) }}</strong></div>
      </section>
      <div class="warning-detail-columns">
        <div class="warning-detail-main">
          <section class="detail-panel">
            <div class="detail-panel-heading">
              <h2>证据定位</h2><span>{{ warning.evidence.length }} 条</span>
            </div>
            <ElEmpty
              v-if="warning.evidence.length === 0"
              description="暂无可用定位"
            />
            <button
              v-for="evidence in warning.evidence"
              :key="evidence.source_span_id"
              class="evidence-row"
              type="button"
              @click="openEvidence(evidence)"
            >
              <span class="evidence-location">{{ evidence.page_no ? `第 ${evidence.page_no} 页` : '原文定位' }}</span>
              <span>{{ evidence.quote }}</span>
            </button>
          </section>
          <section class="detail-panel">
            <div class="detail-panel-heading">
              <h2>事件时间线</h2><span>只读历史</span>
            </div>
            <ol class="warning-timeline">
              <li
                v-for="event in warning.events"
                :key="event.event_id"
              >
                <span class="timeline-dot" />
                <div>
                  <strong>{{ eventLabel(event.event_type) }}</strong><span class="timeline-time">{{ formatDate(event.created_at) }}</span><p v-if="event.note">
                    {{ event.note }}
                  </p><small>{{ event.from_status ? `${statusLabels[event.from_status]} → ${statusLabels[event.to_status ?? event.from_status]}` : statusLabels[event.to_status ?? warning.status] }} · {{ event.actor_id ? event.actor_id.slice(0, 8) : '系统' }}</small>
                </div>
              </li>
            </ol>
          </section>
        </div>
        <aside class="warning-action-panel">
          <h2>处置操作</h2>
          <p
            v-if="!canWrite"
            class="muted-copy"
          >
            当前角色仅可查看预警和证据。
          </p>
          <template v-if="canWrite">
            <ElButton
              v-if="warning.status === 'pending_confirmation'"
              type="primary"
              :icon="CircleCheck"
              @click="submit('confirm')"
            >
              确认并开始处理
            </ElButton>
            <ElButton
              v-if="warning.status === 'pending_confirmation' || warning.status === 'in_progress'"
              :icon="User"
              @click="openAction('assign')"
            >
              分派责任人
            </ElButton>
            <ElButton
              v-if="warning.status === 'pending_confirmation' || warning.status === 'in_progress'"
              :icon="EditPen"
              @click="openAction('note')"
            >
              添加说明
            </ElButton>
            <ElButton
              v-if="warning.status === 'pending_confirmation' || warning.status === 'in_progress'"
              type="warning"
              :icon="Close"
              @click="confirmAction('ignore')"
            >
              忽略预警
            </ElButton>
            <ElButton
              v-if="warning.status === 'pending_confirmation' || warning.status === 'in_progress'"
              type="danger"
              @click="confirmAction('false_positive')"
            >
              标记误报
            </ElButton>
            <ElButton
              v-if="warning.status === 'in_progress'"
              type="success"
              @click="submit('resolve')"
            >
              标记已解决
            </ElButton>
            <ElButton
              v-if="warning.status === 'resolved'"
              type="danger"
              @click="openAction('close')"
            >
              关闭预警
            </ElButton>
            <ElButton
              v-if="canReopen"
              type="primary"
              @click="confirmAction('reopen')"
            >
              重新打开
            </ElButton>
          </template>
          <div
            v-if="warning.resolution"
            class="resolution-box"
          >
            <span>关闭结论</span><p>{{ warning.resolution }}</p>
          </div>
        </aside>
      </div>
    </template>
    <ElSkeleton
      v-else
      :rows="8"
      animated
    />

    <ElDialog
      v-model="actionOpen"
      :title="actionType === 'assign' ? '分派责任人' : actionType === 'close' ? '关闭预警' : '添加说明'"
      width="min(560px, calc(100vw - 32px))"
    >
      <ElForm label-position="top">
        <ElFormItem
          v-if="actionType === 'assign'"
          label="责任人"
          required
        >
          <ElInput
            v-model="assigneeId"
            placeholder="同组织 active reviewer 的用户 ID"
            aria-label="责任人 ID"
          />
        </ElFormItem>
        <ElFormItem
          v-if="actionType === 'assign'"
          label="截止时间"
        >
          <ElDatePicker
            v-model="dueAt"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm"
            placeholder="选择截止时间"
          />
        </ElFormItem>
        <ElFormItem
          v-if="actionType === 'note' || actionType === 'assign'"
          label="说明"
          :required="actionType === 'note'"
        >
          <ElInput
            v-model="note"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            aria-label="预警说明"
          />
        </ElFormItem>
        <ElFormItem
          v-if="actionType === 'close'"
          label="关闭结论"
          required
        >
          <ElInput
            v-model="resolution"
            type="textarea"
            :rows="4"
            maxlength="5000"
            aria-label="关闭结论"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="actionOpen = false">
          取消
        </ElButton><ElButton
          type="primary"
          :loading="submitting"
          @click="submit()"
        >
          提交
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
