<script setup lang="ts">
import { Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  inviteOrganizationMember,
  listOrganizationMembers,
  resendOrganizationInvitation,
  updateOrganizationMember,
} from '@/api/organizations'
import type { Membership, MembershipRole, MembershipStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const organizationId = computed(() => String(route.params.organizationId ?? ''))
const items = ref<Membership[]>([])
const loading = ref(true)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const search = ref('')
const role = ref<MembershipRole | ''>('')
const status = ref<MembershipStatus | ''>('')
const sort = ref<'created_at' | 'display_name'>('created_at')
const direction = ref<'asc' | 'desc'>('desc')
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const forbidden = ref(false)
const actionError = ref('')
const actionRequestId = ref<string | undefined>()

const inviteVisible = ref(false)
const inviteSubmitting = ref(false)
const inviteError = ref('')
const inviteForm = ref<{ email: string; role: MembershipRole }>({ email: '', role: 'reviewer' })

const editingMember = ref<Membership | null>(null)
const editSubmitting = ref(false)
const editError = ref('')
const editRole = ref<MembershipRole>('reviewer')
const editStatus = ref<'active' | 'disabled'>('active')
const resendId = ref<string | null>(null)

const hasFilters = computed(() => Boolean(search.value.trim() || role.value || status.value))

function newIdempotencyKey(prefix: string): string {
  return globalThis.crypto?.randomUUID?.() ?? `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatDate(value: string | null): string {
  if (!value) return '未发送'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function roleLabel(value: MembershipRole): string {
  return { org_admin: '组织管理员', reviewer: '审核员', viewer: '查看者' }[value]
}

function statusLabel(value: MembershipStatus): string {
  return { pending_invitation: '待接受邀请', active: '启用', disabled: '已停用' }[value]
}

function deliveryLabel(value: Membership['email_delivery_status']): string {
  if (value === 'queued') return '投递中'
  if (value === 'sent') return '已发送'
  if (value === 'failed') return '投递失败'
  return '未发送'
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
    const page = await listOrganizationMembers(organizationId.value, {
      q: search.value.trim() || undefined,
      role: role.value || undefined,
      status: status.value || undefined,
      sort: sort.value,
      direction: direction.value,
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

function openInvite(): void {
  inviteForm.value = { email: '', role: 'reviewer' }
  inviteError.value = ''
  inviteVisible.value = true
}

async function invite(): Promise<void> {
  const email = inviteForm.value.email.trim()
  if (!email || !email.includes('@')) {
    inviteError.value = '请输入有效的成员邮箱。'
    return
  }
  if (inviteSubmitting.value) return
  inviteSubmitting.value = true
  inviteError.value = ''
  try {
    await inviteOrganizationMember(
      organizationId.value,
      { email, role: inviteForm.value.role },
      newIdempotencyKey('member-invite'),
    )
    inviteVisible.value = false
    await load()
  } catch (error) {
    const safe = toSafeDisplayError(error)
    inviteError.value = safe.message
  } finally {
    inviteSubmitting.value = false
  }
}

function openEdit(member: Membership): void {
  editingMember.value = member
  editRole.value = member.role
  editStatus.value = member.status === 'disabled' ? 'disabled' : 'active'
  editError.value = ''
}

async function confirmEdit(member: Membership): Promise<boolean> {
  const disabling = member.status === 'active' && editStatus.value === 'disabled'
  const removingAdmin = member.role === 'org_admin' && editRole.value !== 'org_admin'
  if (!disabling && !removingAdmin) return true
  try {
    await ElMessageBox.confirm(
      disabling
        ? '停用成员后，该成员的现有会话将被撤销。确定继续吗？'
        : '降低组织管理员权限可能影响组织管理能力。确定继续吗？',
      '确认成员变更',
      { type: 'warning', confirmButtonText: '确认变更', cancelButtonText: '取消' },
    )
    return true
  } catch {
    return false
  }
}

async function saveEdit(): Promise<void> {
  const member = editingMember.value
  if (!member || editSubmitting.value || !(await confirmEdit(member))) return
  editSubmitting.value = true
  editError.value = ''
  const body: { role?: MembershipRole; status?: 'active' | 'disabled'; version: number } = {
    version: member.version,
  }
  if (editRole.value !== member.role) body.role = editRole.value
  if (member.status !== 'pending_invitation' && editStatus.value !== member.status) {
    body.status = editStatus.value
  }
  try {
    await updateOrganizationMember(member.id, body)
    editingMember.value = null
    await load()
  } catch (error) {
    const safe = toSafeDisplayError(error)
    editError.value = safe.message
    if (error instanceof ApiError && error.code === 'RESOURCE_VERSION_CONFLICT') await load()
  } finally {
    editSubmitting.value = false
  }
}

async function resend(member: Membership): Promise<void> {
  if (member.status !== 'pending_invitation' || resendId.value) return
  try {
    await ElMessageBox.confirm(
      '重发后，之前的邀请链接将立即失效。确定重发吗？',
      '确认重发邀请',
      { confirmButtonText: '重发邀请', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  resendId.value = member.id
  actionError.value = ''
  try {
    await resendOrganizationInvitation(member.id, newIdempotencyKey('member-resend'))
    await load()
  } catch (error) {
    setActionError(error)
  } finally {
    resendId.value = null
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page members-page">
    <div class="page-heading">
      <div>
        <h1>成员管理</h1>
        <p>管理组织成员、角色和邀请投递状态。</p>
      </div>
      <ElButton
        type="primary"
        :icon="Plus"
        @click="openInvite"
      >
        邀请成员
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
      title="无法访问成员管理"
      :description="errorMessage || '当前账户没有组织管理员权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="成员列表加载失败"
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
        class="filter-panel members-filter"
        aria-label="成员筛选"
      >
        <ElInput
          v-model="search"
          clearable
          placeholder="搜索姓名或邮箱"
          aria-label="搜索成员"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="role"
          clearable
          placeholder="角色：全部"
          aria-label="成员角色"
        >
          <ElOption
            label="全部角色"
            value=""
          />
          <ElOption
            label="组织管理员"
            value="org_admin"
          />
          <ElOption
            label="审核员"
            value="reviewer"
          />
          <ElOption
            label="查看者"
            value="viewer"
          />
        </ElSelect>
        <ElSelect
          v-model="status"
          clearable
          placeholder="状态：全部"
          aria-label="成员状态"
        >
          <ElOption
            label="全部状态"
            value=""
          />
          <ElOption
            label="待接受邀请"
            value="pending_invitation"
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
        <ElSelect
          v-model="sort"
          aria-label="成员排序字段"
        >
          <ElOption
            label="创建时间"
            value="created_at"
          />
          <ElOption
            label="显示名称"
            value="display_name"
          />
        </ElSelect>
        <ElSelect
          v-model="direction"
          aria-label="成员排序方向"
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
          :disabled="!hasFilters && !search"
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
          description="暂无成员"
        >
          <ElButton
            v-if="!hasFilters"
            type="primary"
            :icon="Plus"
            @click="openInvite"
          >
            邀请第一位成员
          </ElButton>
          <span v-else>请调整筛选条件。</span>
        </ElEmpty>
        <ElTable
          v-else
          :data="items"
          row-key="id"
          aria-label="组织成员表"
        >
          <ElTableColumn
            label="成员"
            min-width="210"
          >
            <template #default="scope">
              <div class="member-name">
                {{ scope.row.display_name || '未设置姓名' }}
              </div>
              <div class="member-email">
                {{ scope.row.email }}
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="角色"
            width="130"
          >
            <template #default="scope">
              <ElTag effect="plain">
                {{ roleLabel(scope.row.role) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="140"
          >
            <template #default="scope">
              <ElTag
                :type="scope.row.status === 'active' ? 'success' : scope.row.status === 'disabled' ? 'info' : 'warning'"
                effect="light"
              >
                {{ statusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="邀请投递"
            width="130"
          >
            <template #default="scope">
              <ElTag
                v-if="scope.row.email_delivery_status"
                :type="scope.row.email_delivery_status === 'failed' ? 'danger' : scope.row.email_delivery_status === 'sent' ? 'success' : 'warning'"
                effect="plain"
              >
                {{ deliveryLabel(scope.row.email_delivery_status) }}
              </ElTag>
              <span
                v-else
                class="muted-text"
              >未发送</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="邀请/创建时间"
            min-width="170"
          >
            <template #default="scope">
              <span>{{ formatDate(scope.row.invited_at || scope.row.created_at) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="190"
            fixed="right"
          >
            <template #default="scope">
              <ElButton
                text
                type="primary"
                :icon="Edit"
                @click="openEdit(scope.row)"
              >
                编辑
              </ElButton>
              <ElButton
                v-if="scope.row.status === 'pending_invitation'"
                text
                :icon="Refresh"
                :loading="resendId === scope.row.id"
                @click="resend(scope.row)"
              >
                重发
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div
          v-if="items.length > 0"
          class="table-footer"
        >
          <span>当前显示 {{ items.length }} 位成员</span>
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
      v-model="inviteVisible"
      title="邀请成员"
      width="480px"
      destroy-on-close
    >
      <ElAlert
        v-if="inviteError"
        :title="inviteError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <ElForm
        label-position="top"
        class="admin-form"
        @submit.prevent="invite"
      >
        <ElFormItem
          label="成员邮箱"
          required
        >
          <ElInput
            v-model="inviteForm.email"
            type="email"
            autocomplete="email"
            aria-label="成员邮箱"
            placeholder="name@company.com"
          />
        </ElFormItem>
        <ElFormItem
          label="分配角色"
          required
        >
          <ElSelect
            v-model="inviteForm.role"
            aria-label="邀请角色"
          >
            <ElOption
              label="组织管理员"
              value="org_admin"
            />
            <ElOption
              label="审核员"
              value="reviewer"
            />
            <ElOption
              label="查看者"
              value="viewer"
            />
          </ElSelect>
        </ElFormItem>
        <p class="form-hint">
          系统会发送一次性邀请链接；页面不会显示或保存邀请令牌。
        </p>
      </ElForm>
      <template #footer>
        <ElButton @click="inviteVisible = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="inviteSubmitting"
          @click="invite"
        >
          发送邀请
        </ElButton>
      </template>
    </ElDialog>

    <ElDialog
      :model-value="Boolean(editingMember)"
      title="编辑成员"
      width="480px"
      @close="editingMember = null"
    >
      <ElAlert
        v-if="editError"
        :title="editError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <p
        v-if="editingMember"
        class="dialog-context"
      >
        {{ editingMember.display_name || editingMember.email }} · {{ editingMember.email }}
      </p>
      <ElForm
        label-position="top"
        class="admin-form"
      >
        <ElFormItem label="角色">
          <ElSelect
            v-model="editRole"
            aria-label="编辑角色"
          >
            <ElOption
              label="组织管理员"
              value="org_admin"
            />
            <ElOption
              label="审核员"
              value="reviewer"
            />
            <ElOption
              label="查看者"
              value="viewer"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="状态">
          <ElSelect
            v-model="editStatus"
            aria-label="编辑状态"
            :disabled="editingMember?.status === 'pending_invitation'"
          >
            <ElOption
              label="启用"
              value="active"
            />
            <ElOption
              label="已停用"
              value="disabled"
            />
          </ElSelect>
          <span
            v-if="editingMember?.status === 'pending_invitation'"
            class="form-hint"
          >
            成员接受邀请后才能启用。
          </span>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="editingMember = null">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="editSubmitting"
          @click="saveEdit"
        >
          保存变更
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
