<script setup lang="ts">
import { Lock, Plus } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createSupportAccessGrant,
  listSupportAccessGrants,
  revokeSupportAccessGrant,
} from '@/api/organizations'
import type { SupportAccessGrant, SupportAccessGrantStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const organizationId = computed(() => String(route.params.organizationId ?? ''))
const items = ref<SupportAccessGrant[]>([])
const loading = ref(true)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const status = ref<SupportAccessGrantStatus | ''>('')
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string | undefined>()
const createVisible = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref<{ platform_admin_user_id: string; reason: string; expires_at: Date | null }>({
  platform_admin_user_id: '',
  reason: '',
  expires_at: new Date(Date.now() + 60 * 60 * 1000),
})
const selectedGrant = ref<SupportAccessGrant | null>(null)
const drawerVisible = ref(false)
const revokingId = ref<string | null>(null)

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `support-grant-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function statusLabel(value: SupportAccessGrantStatus): string {
  return { active: '活跃', expired: '已过期', revoked: '已撤销' }[value]
}

function remainingLabel(value: string): string {
  const remaining = new Date(value).getTime() - Date.now()
  if (remaining <= 0) return '即将过期'
  const minutes = Math.ceil(remaining / 60_000)
  if (minutes < 60) return `剩余 ${minutes} 分钟`
  return `剩余 ${Math.ceil(minutes / 60)} 小时`
}

function resetListError(): void {
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
}

function setActionError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  actionError.value = safe.message
  actionRequestId.value = safe.requestId
}

async function load(reset = true): Promise<void> {
  if (reset) nextCursor.value = null
  loading.value = true
  resetListError()
  try {
    const page = await listSupportAccessGrants(organizationId.value, {
      status: status.value || undefined,
      sort: 'created_at',
      direction: 'desc',
      limit: 20,
      cursor: reset ? undefined : nextCursor.value ?? undefined,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.value = {
    platform_admin_user_id: '',
    reason: '',
    expires_at: new Date(Date.now() + 60 * 60 * 1000),
  }
  createError.value = ''
  createVisible.value = true
}

function isDateDisabled(date: Date): boolean {
  const max = Date.now() + 4 * 60 * 60 * 1000
  return date.getTime() < Date.now() - 24 * 60 * 60 * 1000 || date.getTime() > max
}

async function create(): Promise<void> {
  const expiresAt = form.value.expires_at
  const now = Date.now()
  if (!form.value.platform_admin_user_id.trim()) {
    createError.value = '请输入平台管理员用户 ID。'
    return
  }
  if (!form.value.reason.trim()) {
    createError.value = '请填写授权原因。'
    return
  }
  if (!expiresAt || expiresAt.getTime() <= now || expiresAt.getTime() > now + 4 * 60 * 60 * 1000) {
    createError.value = '到期时间必须晚于当前时间且不超过 4 小时。'
    return
  }
  try {
    await ElMessageBox.confirm(
      '该授权仅允许平台支持人员只读访问 JSON，不能修改或下载业务数据，最长 4 小时且每次访问都会被审计。确定创建吗？',
      '确认创建只读支持授权',
      { type: 'warning', confirmButtonText: '确认授权', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    await createSupportAccessGrant(
      organizationId.value,
      {
        platform_admin_user_id: form.value.platform_admin_user_id.trim(),
        reason: form.value.reason.trim(),
        expires_at: expiresAt.toISOString(),
      },
      newIdempotencyKey(),
    )
    createVisible.value = false
    await load()
  } catch (error) {
    const safe = toSafeDisplayError(error)
    createError.value = safe.message
    if (error instanceof ApiError && error.code === 'ACTIVE_SUPPORT_GRANT_EXISTS') await load()
  } finally {
    creating.value = false
  }
}

async function revoke(grant: SupportAccessGrant): Promise<void> {
  if (grant.status !== 'active' || revokingId.value) return
  try {
    await ElMessageBox.confirm(
      '撤销后平台支持人员将立即失去授权。确定撤销吗？',
      '确认撤销支持授权',
      { type: 'warning', confirmButtonText: '立即撤销', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  revokingId.value = grant.id
  actionError.value = ''
  try {
    await revokeSupportAccessGrant(organizationId.value, grant.id)
    if (selectedGrant.value?.id === grant.id) {
      selectedGrant.value = null
      drawerVisible.value = false
    }
    await load()
  } catch (error) {
    setActionError(error)
  } finally {
    revokingId.value = null
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page support-page">
    <ElAlert
      title="只读支持访问，最长 4 小时，每次访问都会产生审计记录。"
      description="授权不包含写操作或业务文件下载权限。"
      type="info"
      :icon="Lock"
      :closable="false"
      show-icon
    />
    <div class="page-heading">
      <div>
        <h1>支持授权</h1>
        <p>临时授予平台支持人员只读排查权限，并可立即撤销。</p>
      </div>
      <ElButton
        type="primary"
        :icon="Plus"
        @click="openCreate"
      >
        创建支持授权
      </ElButton>
    </div>

    <ElAlert
      v-if="actionError"
      :title="actionError"
      type="error"
      :description="actionRequestId ? `请求 ID：${actionRequestId}` : undefined"
      :closable="false"
      show-icon
    />
    <PageState
      v-if="forbidden"
      title="无法访问支持授权"
      :description="errorMessage || '当前账户没有组织管理员权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="支持授权加载失败"
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
      />
      <section
        class="filter-panel support-filter"
        aria-label="支持授权筛选"
      >
        <ElSelect
          v-model="status"
          aria-label="支持授权状态"
          @change="load()"
        >
          <ElOption
            label="全部状态"
            value=""
          />
          <ElOption
            label="活跃"
            value="active"
          />
          <ElOption
            label="已过期"
            value="expired"
          />
          <ElOption
            label="已撤销"
            value="revoked"
          />
        </ElSelect>
        <ElButton
          :loading="loading"
          @click="load()"
        >
          刷新列表
        </ElButton>
      </section>

      <section class="table-panel support-table-panel">
        <ElSkeleton
          v-if="loading && items.length === 0"
          :rows="5"
          animated
          class="table-skeleton"
        />
        <ElEmpty
          v-else-if="items.length === 0"
          description="暂无支持授权记录"
        >
          <ElButton
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            创建第一条授权
          </ElButton>
        </ElEmpty>
        <ElTable
          v-else
          :data="items"
          row-key="id"
          aria-label="支持授权表"
        >
          <ElTableColumn
            label="平台管理员"
            min-width="200"
          >
            <template #default="scope">
              <span class="technical-value">{{ scope.row.platform_admin_user_id }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="授权原因"
            min-width="230"
            show-overflow-tooltip
          >
            <template #default="scope">
              {{ scope.row.reason }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="创建时间"
            min-width="170"
          >
            <template #default="scope">
              {{ formatDate(scope.row.created_at) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="到期时间"
            min-width="170"
          >
            <template #default="scope">
              <span>{{ formatDate(scope.row.expires_at) }}</span>
              <span
                v-if="scope.row.status === 'active'"
                class="countdown-hint"
              >{{ remainingLabel(scope.row.expires_at) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="120"
          >
            <template #default="scope">
              <ElTag
                :type="scope.row.status === 'active' ? 'success' : scope.row.status === 'revoked' ? 'danger' : 'info'"
                effect="light"
              >
                {{ statusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="150"
            fixed="right"
          >
            <template #default="scope">
              <ElButton
                text
                type="primary"
                @click="selectedGrant = scope.row; drawerVisible = true"
              >
                详情
              </ElButton>
              <ElButton
                v-if="scope.row.status === 'active'"
                text
                type="danger"
                :loading="revokingId === scope.row.id"
                @click="revoke(scope.row)"
              >
                撤销
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div
          v-if="items.length > 0"
          class="table-footer"
        >
          <span>当前显示 {{ items.length }} 条授权</span>
          <ElButton
            :loading="loading"
            :disabled="!hasMore"
            @click="load(false)"
          >
            加载更多
          </ElButton>
        </div>
      </section>
    </template>

    <ElDialog
      v-model="createVisible"
      title="创建支持授权"
      width="520px"
      destroy-on-close
    >
      <ElAlert
        v-if="createError"
        :title="createError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <ElForm
        label-position="top"
        class="admin-form"
      >
        <ElFormItem
          label="平台管理员用户 ID"
          required
        >
          <ElInput
            v-model="form.platform_admin_user_id"
            aria-label="平台管理员用户 ID"
            placeholder="输入平台管理员 UUID"
          />
          <span class="form-hint">服务端会再次验证目标用户是否为有效的平台管理员。</span>
        </ElFormItem>
        <ElFormItem
          label="授权原因"
          required
        >
          <ElInput
            v-model="form.reason"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            aria-label="授权原因"
            placeholder="请描述需要支持排查的问题。"
          />
        </ElFormItem>
        <ElFormItem
          label="到期时间"
          required
        >
          <ElDatePicker
            v-model="form.expires_at"
            type="datetime"
            placeholder="选择到期时间"
            :disabled-date="isDateDisabled"
            aria-label="到期时间"
          />
          <span class="form-hint">必须晚于当前时间，且不超过 4 小时。</span>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createVisible = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="creating"
          @click="create"
        >
          确认授权
        </ElButton>
      </template>
    </ElDialog>

    <ElDrawer
      v-model="drawerVisible"
      title="授权详情"
      size="480px"
      @close="selectedGrant = null"
    >
      <template v-if="selectedGrant">
        <dl class="metadata-list grant-detail-list">
          <div>
            <dt>平台管理员</dt>
            <dd class="technical-value">
              {{ selectedGrant.platform_admin_user_id }}
            </dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>
              <ElTag :type="selectedGrant.status === 'active' ? 'success' : selectedGrant.status === 'revoked' ? 'danger' : 'info'">
                {{ statusLabel(selectedGrant.status) }}
              </ElTag>
            </dd>
          </div>
          <div class="grant-detail-wide">
            <dt>授权原因</dt>
            <dd>{{ selectedGrant.reason }}</dd>
          </div>
          <div>
            <dt>授权人</dt>
            <dd class="technical-value">
              {{ selectedGrant.granted_by }}
            </dd>
          </div>
          <div>
            <dt>创建时间</dt>
            <dd>{{ formatDate(selectedGrant.created_at) }}</dd>
          </div>
          <div>
            <dt>到期时间</dt>
            <dd>{{ formatDate(selectedGrant.expires_at) }}</dd>
          </div>
        </dl>
        <ElAlert
          title="该授权仅限只读 JSON 访问，禁止修改和下载。"
          type="info"
          :closable="false"
          show-icon
        />
      </template>
    </ElDrawer>
  </section>
</template>
