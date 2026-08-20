<script setup lang="ts">
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  createClauseTemplate,
  listClauseTemplates,
} from '@/api/clauseTemplates'
import type {
  ClauseContractType,
  ClauseTemplate,
  ClauseTemplateStatus,
} from '@/api/types'
import PageState from '@/components/PageState.vue'
import {
  activeOrganizationMemberships,
  currentOrganizationId,
} from '@/features/auth/session'

const router = useRouter()
const items = ref<ClauseTemplate[]>([])
const loading = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const cursor = ref<string>()
const hasMore = ref(false)
const search = ref('')
const contractType = ref<ClauseContractType | ''>('')
const scenario = ref('')
const status = ref<ClauseTemplateStatus | ''>('')
const createOpen = ref(false)
const creating = ref(false)
const createError = ref('')
const createRequestId = ref<string>()
const createName = ref('')
const createType = ref<ClauseContractType>('purchase')
const createScenario = ref('standard')
let loadGeneration = 0

const organizationId = currentOrganizationId
const organizationContextMissing = computed(
  () => activeOrganizationMemberships.value.length === 0 || !organizationId.value,
)
const currentMembership = computed(() =>
  activeOrganizationMemberships.value.find(
    (membership) => membership.organization_id === organizationId.value,
  ),
)
const canManage = computed(() => currentMembership.value?.role === 'org_admin')

const contractTypes: Array<{ label: string; value: ClauseContractType }> = [
  { label: '采购合同', value: 'purchase' },
  { label: '销售合同', value: 'sales' },
  { label: '保密协议', value: 'nda' },
  { label: '外包合同', value: 'outsourcing' },
  { label: '劳动合同', value: 'employment' },
]

function contractTypeLabel(value: ClauseContractType): string {
  return contractTypes.find((item) => item.value === value)?.label ?? value
}

function statusLabel(value: ClauseTemplateStatus): string {
  return value === 'active' ? '启用' : '已停用'
}

function versionLabel(template: ClauseTemplate): string {
  return template.current_published_version_id ? '已配置当前版本' : '未发布'
}

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(append = false): Promise<void> {
  if (organizationContextMissing.value) {
    items.value = []
    loading.value = false
    return
  }
  const generation = ++loadGeneration
  if (!append) cursor.value = undefined
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  try {
    const page = await listClauseTemplates(organizationId.value, {
      q: search.value.trim() || undefined,
      contract_type: contractType.value || undefined,
      business_scenario: scenario.value.trim() || undefined,
      status: status.value || undefined,
      cursor: append ? cursor.value : undefined,
      limit: 20,
    })
    if (generation !== loadGeneration) return
    items.value = append ? [...items.value, ...page.items] : page.items
    cursor.value = page.next_cursor ?? undefined
    hasMore.value = page.has_more
  } catch (error) {
    if (generation === loadGeneration) setPageError(error)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function openCreate(): void {
  createName.value = ''
  createType.value = 'purchase'
  createScenario.value = 'standard'
  createError.value = ''
  createRequestId.value = undefined
  createOpen.value = true
}

async function submitCreate(): Promise<void> {
  if (!organizationId.value || !createName.value.trim() || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    const template = await createClauseTemplate(
      organizationId.value,
      {
        name: createName.value.trim(),
        contract_type: createType.value,
        business_scenario: createScenario.value.trim() || 'standard',
      },
      crypto.randomUUID(),
    )
    createOpen.value = false
    await router.push(`/clause-templates/${template.id}`)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    createError.value = safe.message
    createRequestId.value = safe.requestId
  } finally {
    creating.value = false
  }
}

function openTemplate(template: ClauseTemplate): void {
  void router.push(`/clause-templates/${template.id}`)
}

watch(organizationId, () => {
  items.value = []
  void load()
})

onMounted(() => void load())
</script>

<template>
  <section class="admin-page clause-template-list-page">
    <ElResult
      v-if="organizationContextMissing"
      icon="info"
      title="需要选择当前组织"
      sub-title="请在左侧组织选择器中选择要管理的组织。"
    />
    <template v-else>
      <div class="page-heading">
        <div>
          <div class="technical-value">
            知识配置 · CLAUSE-001
          </div>
          <h1>条款模板</h1>
          <p>维护不同合同类型和业务场景的标准条款版本。</p>
        </div>
        <ElButton
          v-if="canManage"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          新建模板
        </ElButton>
      </div>

      <PageState
        v-if="forbidden"
        title="无法访问条款模板"
        :description="errorMessage || '当前账户没有访问权限。'"
        icon="error"
        :request-id="errorRequestId"
        @retry="load"
      />
      <template v-else>
        <section
          class="filter-panel clause-template-filter"
          aria-label="条款模板筛选"
        >
          <ElInput
            v-model="search"
            :prefix-icon="Search"
            clearable
            placeholder="搜索模板名称"
            aria-label="搜索模板名称"
            @keyup.enter="load()"
          />
          <ElSelect
            v-model="contractType"
            clearable
            placeholder="全部合同类型"
            aria-label="合同类型"
          >
            <ElOption
              label="全部合同类型"
              value=""
            />
            <ElOption
              v-for="item in contractTypes"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </ElSelect>
          <ElInput
            v-model="scenario"
            clearable
            placeholder="业务场景"
            aria-label="业务场景"
            @keyup.enter="load()"
          />
          <ElSelect
            v-model="status"
            clearable
            placeholder="全部状态"
            aria-label="模板状态"
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
          <ElButton
            :icon="Refresh"
            :loading="loading"
            @click="load()"
          >
            应用筛选
          </ElButton>
        </section>

        <section class="table-panel">
          <ElAlert
            v-if="errorMessage"
            :title="errorMessage"
            type="error"
            :closable="false"
            show-icon
            class="dialog-alert"
          />
          <ElSkeleton
            v-if="loading && items.length === 0"
            :rows="6"
            animated
            class="table-skeleton"
          />
          <ElEmpty
            v-else-if="items.length === 0"
            description="暂无条款模板"
          >
            <ElButton
              v-if="canManage"
              type="primary"
              :icon="Plus"
              @click="openCreate"
            >
              创建第一套模板
            </ElButton>
          </ElEmpty>
          <ElTable
            v-else
            v-loading="loading"
            :data="items"
            row-key="id"
            aria-label="条款模板列表"
            @row-click="openTemplate"
          >
            <ElTableColumn
              label="模板名称"
              min-width="240"
            >
              <template #default="scope">
                <button
                  class="table-link"
                  type="button"
                  @click.stop="openTemplate(scope.row)"
                >
                  {{ scope.row.name }}
                </button>
                <ElTag
                  v-if="scope.row.is_default"
                  size="small"
                  type="success"
                  class="table-inline-tag"
                >
                  默认
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn
              label="合同类型"
              min-width="150"
            >
              <template #default="scope">
                {{ contractTypeLabel(scope.row.contract_type) }}
              </template>
            </ElTableColumn>
            <ElTableColumn
              label="业务场景"
              min-width="150"
            >
              <template #default="scope">
                <span class="technical-value">{{ scope.row.business_scenario }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn
              label="当前发布"
              min-width="150"
            >
              <template #default="scope">
                {{ versionLabel(scope.row) }}
              </template>
            </ElTableColumn>
            <ElTableColumn
              label="状态"
              width="110"
            >
              <template #default="scope">
                <ElTag :type="scope.row.status === 'active' ? 'success' : 'info'">
                  {{ statusLabel(scope.row.status) }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn
              label="操作"
              width="130"
              align="right"
            >
              <template #default="scope">
                <ElButton
                  link
                  type="primary"
                  @click.stop="openTemplate(scope.row)"
                >
                  查看详情
                </ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
          <div
            v-if="items.length > 0"
            class="table-footer"
          >
            <span>{{ items.length }} 个模板</span>
            <ElButton
              v-if="hasMore"
              :loading="loading"
              @click="load(true)"
            >
              加载更多
            </ElButton>
          </div>
        </section>
      </template>
    </template>

    <ElDialog
      v-model="createOpen"
      title="新建条款模板"
      width="min(560px, calc(100vw - 32px))"
    >
      <ElAlert
        v-if="createError"
        :title="createError"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      >
        <p
          v-if="createRequestId"
          class="request-id"
        >
          请求 ID：{{ createRequestId }}
        </p>
      </ElAlert>
      <ElForm label-position="top">
        <ElFormItem
          label="模板名称"
          required
        >
          <ElInput
            v-model="createName"
            maxlength="255"
            show-word-limit
            aria-label="模板名称"
          />
        </ElFormItem>
        <div class="form-row">
          <ElFormItem
            label="合同类型"
            required
          >
            <ElSelect
              v-model="createType"
              aria-label="合同类型"
            >
              <ElOption
                v-for="item in contractTypes"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="业务场景">
            <ElInput
              v-model="createScenario"
              maxlength="128"
              placeholder="留空使用 standard"
              aria-label="业务场景"
            />
          </ElFormItem>
        </div>
      </ElForm>
      <template #footer>
        <ElButton @click="createOpen = false">
          取消
        </ElButton>
        <ElButton
          type="primary"
          :loading="creating"
          :disabled="!createName.trim()"
          @click="submitCreate"
        >
          创建
        </ElButton>
      </template>
    </ElDialog>
  </section>
</template>
