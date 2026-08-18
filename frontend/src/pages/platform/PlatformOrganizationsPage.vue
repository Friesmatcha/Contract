<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { OfficeBuilding } from '@element-plus/icons-vue'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createPlatformOrganization,
  listPlatformOrganizations,
} from '@/api/organizations'
import type {
  OrganizationStatus,
  PlatformOrganizationListItem,
} from '@/api/types'
import PageState from '@/components/PageState.vue'

const router = useRouter()
const items = ref<PlatformOrganizationListItem[]>([])
const loading = ref(true)
const submitting = ref(false)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const q = ref('')
const status = ref<OrganizationStatus | ''>('')
const sort = ref<'created_at' | 'name'>('created_at')
const direction = ref<'asc' | 'desc'>('desc')
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const forbidden = ref(false)
const dialogVisible = ref(false)
const formError = ref('')
const formRequestId = ref<string | undefined>()
const form = ref({ name: '', initial_admin_email: '', retention_days: 180 })

const hasFilters = computed(() => Boolean(q.value.trim() || status.value))

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `organization-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function resetErrors(): void {
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
}

async function load(reset = true): Promise<void> {
  if (reset) nextCursor.value = null
  loading.value = true
  resetErrors()
  try {
    const page = await listPlatformOrganizations({
      q: q.value.trim() || undefined,
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
    forbidden.value = error instanceof ApiError && error.status === 403
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.value = { name: '', initial_admin_email: '', retention_days: 180 }
  formError.value = ''
  formRequestId.value = undefined
  dialogVisible.value = true
}

async function create(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  formError.value = ''
  formRequestId.value = undefined
  try {
    const created = await createPlatformOrganization(
      {
        name: form.value.name.trim(),
        initial_admin_email: form.value.initial_admin_email.trim(),
        retention_days: form.value.retention_days,
      },
      newIdempotencyKey(),
    )
    dialogVisible.value = false
    await router.push(`/platform/organizations/${created.id}`)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    formError.value = safe.message
    formRequestId.value = safe.requestId
  } finally {
    submitting.value = false
  }
}

function openOrganization(row: PlatformOrganizationListItem): void {
  void router.push(`/platform/organizations/${row.id}`)
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <h1>平台组织</h1>
        <p>检索组织状态并维护平台级组织属性。</p>
      </div>
      <ElButton
        type="primary"
        :icon="OfficeBuilding"
        @click="openCreate"
      >
        新建组织
      </ElButton>
    </div>

    <div
      v-if="forbidden"
      class="page-state-wrap"
    >
      <PageState
        title="无权访问平台组织"
        description="当前账户不是平台管理员，无法查看组织列表。"
        icon="error"
        :request-id="errorRequestId"
        action-label="返回工作区"
        @retry="router.push('/')"
      />
    </div>
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="组织列表加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <template v-else>
      <section
        class="filter-panel"
        aria-label="组织筛选"
      >
        <ElInput
          v-model="q"
          clearable
          placeholder="搜索组织名称"
          aria-label="搜索组织名称"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="status"
          clearable
          placeholder="状态：全部"
          aria-label="组织状态"
          @change="load()"
        >
          <ElOption
            label="全部状态"
            value=""
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
          aria-label="排序字段"
          @change="load()"
        >
          <ElOption
            label="创建时间"
            value="created_at"
          />
          <ElOption
            label="组织名称"
            value="name"
          />
        </ElSelect>
        <ElSelect
          v-model="direction"
          aria-label="排序方向"
          @change="load()"
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
          :disabled="!hasFilters"
          @click="load()"
        >
          应用筛选
        </ElButton>
      </section>

      <section class="table-panel">
        <ElTable
          v-loading="loading"
          :data="items"
          row-key="id"
          aria-label="组织列表"
        >
          <ElTableColumn
            label="组织名称"
            min-width="240"
          >
            <template #default="scope">
              <button
                class="table-link"
                type="button"
                @click="openOrganization(scope.row)"
              >
                {{ scope.row.name }}
              </button>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="120"
          >
            <template #default="scope">
              <ElTag
                :type="scope.row.status === 'active' ? 'success' : 'info'"
                effect="plain"
              >
                {{ scope.row.status === 'active' ? '启用' : '已停用' }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="保留天数"
            width="140"
          >
            <template #default="scope">
              {{ scope.row.retention_days }} 天
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="创建时间"
            min-width="190"
          >
            <template #default="scope">
              <span class="technical-value">{{ formatDate(scope.row.created_at) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="操作"
            width="100"
            align="right"
          >
            <template #default="scope">
              <ElButton
                link
                type="primary"
                @click="openOrganization(scope.row)"
              >
                查看
              </ElButton>
            </template>
          </ElTableColumn>
          <template #empty>
            <ElEmpty
              :description="hasFilters ? '没有匹配的组织' : '暂无组织'"
            >
              <ElButton
                v-if="!hasFilters"
                type="primary"
                @click="openCreate"
              >
                新建组织
              </ElButton>
            </ElEmpty>
          </template>
        </ElTable>
        <div class="table-footer">
          <span>{{ items.length ? `已显示 ${items.length} 个组织` : '暂无组织记录' }}</span>
          <div class="table-footer-actions">
            <ElButton
              :disabled="items.length === 0"
              @click="load()"
            >
              返回首段
            </ElButton>
            <ElButton
              type="primary"
              :disabled="!hasMore || loading"
              @click="load(false)"
            >
              加载更多
            </ElButton>
          </div>
        </div>
      </section>
    </template>

    <ElDialog
      v-model="dialogVisible"
      title="新建组织"
      width="520px"
      :close-on-click-modal="false"
    >
      <ElAlert
        v-if="formError"
        :title="formError"
        type="error"
        :closable="false"
        show-icon
      />
      <p
        v-if="formRequestId"
        class="request-id dialog-request-id"
      >
        请求 ID：{{ formRequestId }}
      </p>
      <ElForm
        class="admin-form"
        label-position="top"
        @submit.prevent="create"
      >
        <ElFormItem
          label="组织名称"
          required
        >
          <ElInput
            v-model="form.name"
            autocomplete="organization"
            maxlength="255"
            show-word-limit
          />
        </ElFormItem>
        <ElFormItem
          label="初始管理员邮箱"
          required
        >
          <ElInput
            v-model="form.initial_admin_email"
            type="email"
            autocomplete="email"
          />
        </ElFormItem>
        <ElFormItem label="保留天数">
          <ElInputNumber
            v-model="form.retention_days"
            :min="0"
            :precision="0"
            controls-position="right"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="submitting"
          :disabled="!form.name.trim() || !form.initial_admin_email.trim()"
          @click="create"
        >
          创建组织
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
