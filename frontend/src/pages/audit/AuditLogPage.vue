<script setup lang="ts">
import { CopyDocument, Refresh, Search, View } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { listOrganizationAuditLogs, listPlatformAuditLogs } from '@/api/audit'
import type { AuditLog, AuditLogQuery } from '@/api/types'
import {
  currentOrganizationId,
  currentOrganizationMembership,
} from '@/features/auth/session'
import PageState from '@/components/PageState.vue'

const props = defineProps<{ scope: 'organization' | 'platform' }>()

const items = ref<AuditLog[]>([])
const loading = ref(true)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const action = ref('')
const resourceType = ref('')
const actorId = ref('')
const organizationFilter = ref('')
const createdFrom = ref('')
const createdTo = ref('')
const errorMessage = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const selected = ref<AuditLog | null>(null)
const drawerVisible = ref(false)

const isPlatform = computed(() => props.scope === 'platform')
const isOrgAdmin = computed(() => currentOrganizationMembership.value?.role === 'org_admin')
const title = computed(() => isPlatform.value ? '平台审计' : '组织审计')
const description = computed(() => isPlatform.value
  ? '跨组织查询只读审计事实和安全变更摘要。'
  : '查询当前组织的只读审计事实和安全变更摘要。')
const hasFilters = computed(() => Boolean(
  action.value.trim() || resourceType.value.trim() || actorId.value.trim() ||
  organizationFilter.value.trim() || createdFrom.value || createdTo.value,
))
const dateError = computed(() => {
  if (!createdFrom.value || !createdTo.value) return ''
  const from = new Date(createdFrom.value)
  const to = new Date(createdTo.value)
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return '时间范围无效。'
  return from >= to ? '开始时间必须早于结束时间。' : ''
})

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function toIso(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

function safeSummary(value: Record<string, unknown> | null): string {
  if (!value) return '无'
  const blocked = /authorization|cookie|contract[_-]?text|csrf|password|prompt|raw[_-]?response|secret|token/i
  const sanitize = (entry: unknown): unknown => {
    if (Array.isArray(entry)) return entry.map(sanitize)
    if (typeof entry !== 'object' || entry === null) return entry
    return Object.fromEntries(
      Object.entries(entry)
        .filter(([key]) => !blocked.test(key))
        .map(([key, nested]) => [key, sanitize(nested)]),
    )
  }
  return JSON.stringify(sanitize(value), null, 2) || '无'
}

async function copy(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('当前浏览器不支持复制。')
  }
}

function resetErrors(): void {
  errorMessage.value = ''
  requestId.value = undefined
  forbidden.value = false
}

function query(cursor?: string): AuditLogQuery {
  return {
    organizationId: isPlatform.value ? undefined : currentOrganizationId.value || undefined,
    organizationFilter: isPlatform.value ? organizationFilter.value.trim() || undefined : undefined,
    action: action.value.trim() || undefined,
    resourceType: resourceType.value.trim() || undefined,
    actorId: actorId.value.trim() || undefined,
    createdFrom: toIso(createdFrom.value),
    createdTo: toIso(createdTo.value),
    limit: 20,
    cursor,
  }
}

async function load(reset = true): Promise<void> {
  if (dateError.value || loading.value && !reset) return
  if (reset) nextCursor.value = null
  loading.value = true
  resetErrors()
  try {
    const page = isPlatform.value
      ? await listPlatformAuditLogs(query(reset ? undefined : nextCursor.value ?? undefined))
      : await listOrganizationAuditLogs(query(reset ? undefined : nextCursor.value ?? undefined))
    items.value = reset ? page.items : [...items.value, ...page.items]
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    loading.value = false
  }
}

function reset(): void {
  action.value = ''
  resourceType.value = ''
  actorId.value = ''
  organizationFilter.value = ''
  createdFrom.value = ''
  createdTo.value = ''
  void load()
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page audit-log-page">
    <PageState
      v-if="forbidden"
      :title="`无法查看${title}`"
      :description="errorMessage || (isPlatform ? '只有平台管理员可以查看平台审计。' : '当前账户没有组织管理员权限。')"
      icon="error"
      :request-id="requestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0 && !loading"
      :title="`${title}加载失败`"
      :description="errorMessage"
      :request-id="requestId"
      @retry="load()"
    />
    <template v-else>
      <div class="page-heading">
        <div>
          <div class="technical-value">
            {{ isPlatform ? 'PLATFORM-004' : 'ADMIN-001' }}
          </div>
          <h1>{{ title }}</h1>
          <p>{{ description }}</p>
        </div>
      </div>

      <ElAlert
        v-if="errorMessage && items.length > 0"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />
      <ElAlert
        v-if="dateError"
        :title="dateError"
        type="warning"
        :closable="false"
        show-icon
      />

      <section
        class="filter-panel audit-filter"
        aria-label="审计日志筛选"
      >
        <ElInput
          v-model="action"
          clearable
          placeholder="动作"
          aria-label="动作"
        />
        <ElInput
          v-model="resourceType"
          clearable
          placeholder="资源类型"
          aria-label="资源类型"
        />
        <ElInput
          v-model="actorId"
          clearable
          placeholder="操作者 ID"
          aria-label="操作者 ID"
        />
        <ElInput
          v-if="isPlatform"
          v-model="organizationFilter"
          clearable
          placeholder="组织 ID"
          aria-label="组织 ID"
        />
        <ElInput
          v-model="createdFrom"
          type="datetime-local"
          aria-label="开始时间"
        />
        <ElInput
          v-model="createdTo"
          type="datetime-local"
          aria-label="结束时间"
        />
        <ElButton
          type="primary"
          :icon="Search"
          :disabled="Boolean(dateError) || (isPlatform ? false : !isOrgAdmin)"
          :loading="loading"
          @click="load()"
        >
          筛选
        </ElButton>
        <ElButton
          :icon="Refresh"
          :disabled="loading"
          @click="reset"
        >
          重置
        </ElButton>
      </section>

      <section class="table-panel audit-table-panel">
        <ElSkeleton
          v-if="loading && items.length === 0"
          :rows="6"
          animated
          class="table-skeleton"
        />
        <ElEmpty
          v-else-if="items.length === 0"
          :description="hasFilters ? '当前筛选暂无审计事件' : '暂无审计事件'"
        />
        <ElTable
          v-else
          :data="items"
          row-key="id"
          aria-label="审计日志表"
        >
          <ElTableColumn
            label="时间"
            width="180"
          >
            <template #default="row">
              <span class="technical-value">{{ formatDate(row.row.created_at) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="动作"
            min-width="190"
          >
            <template #default="row">
              <span class="technical-value">{{ row.row.action }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            v-if="isPlatform"
            label="组织"
            min-width="170"
          >
            <template #default="row">
              <span class="technical-value">{{ row.row.organization_id || '平台' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="资源"
            min-width="190"
          >
            <template #default="row">
              <span>{{ row.row.resource_type }}</span>
              <span
                v-if="row.row.resource_id"
                class="muted-text technical-value"
              > / {{ row.row.resource_id }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作者"
            min-width="170"
          >
            <template #default="row">
              <span class="technical-value">{{ row.row.actor_id || '系统' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="request_id"
            min-width="190"
          >
            <template #default="row">
              <span class="technical-value">{{ row.row.request_id }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="摘要"
            width="90"
            align="right"
          >
            <template #default="row">
              <ElButton
                link
                type="primary"
                :icon="View"
                aria-label="查看安全摘要"
                @click="selected = row.row; drawerVisible = true"
              >
                查看
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div class="table-footer">
          <span>{{ items.length ? `已显示 ${items.length} 条审计事件` : '暂无审计事件' }}</span>
          <div class="table-footer-actions">
            <ElButton
              :icon="Refresh"
              :disabled="loading"
              @click="load()"
            >
              重新加载
            </ElButton>
            <ElButton
              type="primary"
              :disabled="!hasMore || loading"
              @click="load(false)"
            >
              加载下一页
            </ElButton>
          </div>
        </div>
      </section>
    </template>

    <ElDrawer
      v-model="drawerVisible"
      title="安全摘要"
      size="460px"
    >
      <template v-if="selected">
        <dl class="metadata-list audit-detail-list">
          <div>
            <dt>动作</dt><dd class="technical-value">
              {{ selected.action }}
            </dd>
          </div>
          <div><dt>资源类型</dt><dd>{{ selected.resource_type }}</dd></div>
          <div>
            <dt>资源 ID</dt><dd class="technical-value">
              {{ selected.resource_id || '无' }}
            </dd>
          </div>
          <div>
            <dt>操作者</dt><dd class="technical-value">
              {{ selected.actor_id || '系统' }}
            </dd>
          </div>
          <div><dt>发生时间</dt><dd>{{ formatDate(selected.created_at) }}</dd></div>
          <div class="audit-detail-wide">
            <dt>request_id</dt><dd class="technical-value">
              {{ selected.request_id }}
            </dd>
          </div>
        </dl>
        <div class="audit-drawer-actions">
          <ElButton
            :icon="CopyDocument"
            @click="copy(selected.request_id)"
          >
            复制 request_id
          </ElButton>
        </div>
        <h2 class="dialog-section-title">
          变更前摘要
        </h2>
        <pre class="audit-summary">{{ safeSummary(selected.before_summary) }}</pre>
        <h2 class="dialog-section-title">
          变更后摘要
        </h2>
        <pre class="audit-summary">{{ safeSummary(selected.after_summary) }}</pre>
      </template>
    </ElDrawer>
  </section>
</template>
