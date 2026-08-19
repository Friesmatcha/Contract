<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { listContracts } from '@/api/contracts'
import type { Contract, ContractListQuery, ContractStatus, ContractType } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { sessionState } from '@/features/auth/session'

const router = useRouter()
const organizationId = computed(() =>
  sessionState.current?.memberships.find((membership) => membership.status === 'active')?.organization_id ?? '',
)
const role = computed(() =>
  sessionState.current?.memberships.find(
    (membership) => membership.organization_id === organizationId.value,
  )?.role,
)
const canCreate = computed(() => role.value === 'org_admin' || role.value === 'reviewer')

const items = ref<Contract[]>([])
const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const search = ref('')
const ownerId = ref('')
const status = ref<ContractStatus | ''>('active')
const declaredType = ref<ContractType | ''>('')
const sort = ref<ContractListQuery['sort']>('created_at')
const direction = ref<ContractListQuery['direction']>('desc')

function typeLabel(value: ContractType | null): string {
  if (!value) return '未声明'
  return {
    purchase: '采购',
    sales: '销售',
    nda: '保密协议',
    outsourcing: '服务外包',
    employment: '劳动',
    other: '其他/待确认',
  }[value]
}

function statusLabel(value: ContractStatus): string {
  return value === 'active' ? '活跃' : '已归档'
}

function statusType(value: ContractStatus): 'success' | 'info' {
  return value === 'active' ? 'success' : 'info'
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value))
}

function resetError(): void {
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
}

async function load(reset = true): Promise<void> {
  if (!organizationId.value) {
    loading.value = false
    return
  }
  loading.value = true
  resetError()
  if (reset) nextCursor.value = null
  try {
    const page = await listContracts(organizationId.value, {
      q: search.value.trim() || undefined,
      owner_id: ownerId.value.trim() || undefined,
      status: status.value || undefined,
      declared_type: declaredType.value || undefined,
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

function openContract(contract: Contract): void {
  void router.push(`/contracts/${contract.id}`)
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page contracts-page">
    <div class="page-heading">
      <div>
        <h1>合同目录</h1>
        <p>管理合同元数据，按权限查看可用合同。</p>
      </div>
      <ElButton
        v-if="canCreate"
        type="primary"
        :icon="Plus"
        @click="router.push('/contracts/new')"
      >
        创建合同
      </ElButton>
    </div>

    <PageState
      v-if="forbidden"
      title="无法访问合同目录"
      :description="errorMessage || '当前账户没有合同访问权限。'"
      icon="error"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && items.length === 0"
      title="合同目录加载失败"
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
        class="filter-panel contracts-filter"
        aria-label="合同筛选"
      >
        <ElInput
          v-model="search"
          clearable
          placeholder="搜索合同名称或编号"
          aria-label="搜索合同"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="status"
          aria-label="合同状态"
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
            label="已归档"
            value="archived"
          />
        </ElSelect>
        <ElSelect
          v-model="declaredType"
          clearable
          placeholder="合同类型：全部"
          aria-label="合同类型"
        >
          <ElOption
            label="全部类型"
            value=""
          />
          <ElOption
            label="采购"
            value="purchase"
          />
          <ElOption
            label="销售"
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
            label="劳动"
            value="employment"
          />
          <ElOption
            label="其他/待确认"
            value="other"
          />
        </ElSelect>
        <ElInput
          v-model="ownerId"
          clearable
          placeholder="负责人 ID"
          aria-label="负责人 ID"
          @keyup.enter="load()"
        />
        <ElSelect
          v-model="sort"
          aria-label="合同排序字段"
        >
          <ElOption
            label="创建时间"
            value="created_at"
          />
          <ElOption
            label="更新时间"
            value="updated_at"
          />
          <ElOption
            label="合同名称"
            value="title"
          />
        </ElSelect>
        <ElSelect
          v-model="direction"
          aria-label="合同排序方向"
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
          :icon="Refresh"
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
          :description="search || ownerId || declaredType ? '没有符合筛选条件的合同' : '暂无合同'"
        >
          <ElButton
            v-if="canCreate && !search && !ownerId && !declaredType"
            type="primary"
            :icon="Plus"
            @click="router.push('/contracts/new')"
          >
            创建第一份合同
          </ElButton>
        </ElEmpty>
        <ElTable
          v-else
          :data="items"
          row-key="id"
          aria-label="合同目录表"
        >
          <ElTableColumn
            label="合同编号"
            width="190"
          >
            <template #default="scope">
              <button
                class="table-link technical-value"
                type="button"
                @click="openContract(scope.row)"
              >
                {{ scope.row.display_no }}
              </button>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="合同名称"
            min-width="260"
          >
            <template #default="scope">
              <button
                class="table-link"
                type="button"
                @click="openContract(scope.row)"
              >
                {{ scope.row.title }}
              </button>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="声明类型"
            width="150"
          >
            <template #default="scope">
              {{ typeLabel(scope.row.declared_type) }}
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="状态"
            width="120"
          >
            <template #default="scope">
              <ElTag
                :type="statusType(scope.row.status)"
                effect="light"
              >
                {{ statusLabel(scope.row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn
            label="更新时间"
            width="150"
          >
            <template #default="scope">
              {{ formatDate(scope.row.updated_at) }}
            </template>
          </ElTableColumn>
        </ElTable>
        <div
          v-if="items.length > 0"
          class="table-footer"
        >
          <span>当前显示 {{ items.length }} 份合同</span>
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
  </section>
</template>
