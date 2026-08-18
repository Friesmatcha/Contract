<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  getPlatformOrganization,
  updatePlatformOrganization,
} from '@/api/organizations'
import type { Organization, OrganizationStatus } from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const router = useRouter()
const organizationId = computed(() => String(route.params.organizationId ?? ''))
const organization = ref<Organization | null>(null)
const draft = ref({ name: '', status: 'active' as OrganizationStatus, retention_days: 180 })
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const conflictMessage = ref('')
const forbidden = ref(false)

const changed = computed(() => {
  if (!organization.value) return false
  return (
    draft.value.name.trim() !== organization.value.name ||
    draft.value.status !== organization.value.status ||
    draft.value.retention_days !== organization.value.retention_days
  )
})

function applyResource(resource: Organization): void {
  organization.value = resource
  draft.value = {
    name: resource.name,
    status: resource.status,
    retention_days: resource.retention_days,
  }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  try {
    applyResource(await getPlatformOrganization(organizationId.value))
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && error.status === 403
  } finally {
    loading.value = false
  }
}

async function confirmStatusChange(): Promise<boolean> {
  if (draft.value.status !== 'disabled' || organization.value?.status === 'disabled') return true
  try {
    await ElMessageBox.confirm(
      '停用组织会立即撤销成员会话并阻止组织访问。确定继续吗？',
      '确认停用组织',
      { type: 'warning', confirmButtonText: '停用组织', cancelButtonText: '取消' },
    )
    return true
  } catch {
    draft.value.status = organization.value?.status ?? 'active'
    return false
  }
}

async function save(): Promise<void> {
  if (!organization.value || saving.value || !changed.value) return
  if (!(await confirmStatusChange())) return
  saving.value = true
  errorMessage.value = ''
  conflictMessage.value = ''
  try {
    const body: { name?: string; status?: OrganizationStatus; retention_days?: number; version: number } = {
      version: organization.value.version,
    }
    if (draft.value.name.trim() !== organization.value.name) body.name = draft.value.name.trim()
    if (draft.value.status !== organization.value.status) body.status = draft.value.status
    if (draft.value.retention_days !== organization.value.retention_days) {
      body.retention_days = draft.value.retention_days
    }
    applyResource(await updatePlatformOrganization(organizationId.value, body))
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    if (
      error instanceof ApiError &&
      (error.code === 'RESOURCE_VERSION_CONFLICT' || error.code === 'ORGANIZATION_NAME_CONFLICT')
    ) {
      conflictMessage.value = error.message
      await load()
    }
  } finally {
    saving.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <button
          class="back-link"
          type="button"
          @click="router.push('/platform/organizations')"
        >
          返回组织列表
        </button>
        <h1>组织详情</h1>
        <p v-if="organization">
          维护组织名称、状态与数据保留策略。
        </p>
      </div>
      <div class="page-heading-actions">
        <ElTag
          v-if="organization"
          :type="organization.status === 'active' ? 'success' : 'info'"
          effect="plain"
        >
          {{ organization.status === 'active' ? '启用' : '已停用' }}
        </ElTag>
        <ElButton
          type="primary"
          :loading="saving"
          :disabled="!changed || loading"
          @click="save"
        >
          保存修改
        </ElButton>
      </div>
    </div>

    <PageState
      v-if="forbidden"
      title="无权访问组织详情"
      description="当前账户不是平台管理员，无法查看该组织。"
      icon="error"
      :request-id="errorRequestId"
      action-label="返回组织列表"
      @retry="router.push('/platform/organizations')"
    />
    <PageState
      v-else-if="errorMessage && !organization"
      title="组织详情加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <template v-else-if="organization">
      <ElAlert
        v-if="conflictMessage"
        :title="conflictMessage"
        description="页面已刷新为服务端最新版本，请重新确认并提交你的修改。"
        type="warning"
        :closable="false"
        show-icon
      />
      <ElAlert
        v-else-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <div class="detail-grid">
        <section class="summary-panel">
          <h2>基本信息</h2>
          <dl class="metadata-list metadata-list-single">
            <div>
              <dt>组织 ID</dt>
              <dd class="technical-value">
                {{ organization.id }}
              </dd>
            </div>
            <div>
              <dt>当前版本</dt>
              <dd class="technical-value">
                v{{ organization.version }}
              </dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ new Intl.DateTimeFormat('zh-CN').format(new Date(organization.created_at)) }}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{{ new Intl.DateTimeFormat('zh-CN').format(new Date(organization.updated_at)) }}</dd>
            </div>
          </dl>
        </section>

        <section class="form-panel">
          <h2>组织属性</h2>
          <ElForm
            class="admin-form"
            label-position="top"
          >
            <ElFormItem label="组织名称">
              <ElInput
                v-model="draft.name"
                maxlength="255"
                show-word-limit
              />
            </ElFormItem>
            <div class="form-row">
              <ElFormItem label="运行状态">
                <ElSelect v-model="draft.status">
                  <ElOption
                    label="启用"
                    value="active"
                  />
                  <ElOption
                    label="已停用"
                    value="disabled"
                  />
                </ElSelect>
              </ElFormItem>
              <ElFormItem label="保留天数">
                <ElInputNumber
                  v-model="draft.retention_days"
                  :min="0"
                  :precision="0"
                  controls-position="right"
                />
              </ElFormItem>
            </div>
          </ElForm>
        </section>
      </div>

      <section class="summary-panel">
        <h2>非秘密设置摘要</h2>
        <dl class="metadata-list">
          <div>
            <dt>文件大小上限</dt>
            <dd>{{ organization.settings.file_size_limit_bytes }} bytes</dd>
          </div>
          <div>
            <dt>页数上限</dt>
            <dd>{{ organization.settings.page_limit }} 页</dd>
          </div>
          <div>
            <dt>中风险预警</dt>
            <dd>{{ organization.settings.warn_on_medium_risk ? '已启用' : '未启用' }}</dd>
          </div>
          <div>
            <dt>报告水印</dt>
            <dd>{{ organization.settings.report_watermark }}</dd>
          </div>
        </dl>
      </section>

      <section class="danger-panel">
        <div>
          <h2>停用组织</h2>
          <p>停用会撤销组织成员的现有会话，并阻止组织资料和设置访问。</p>
        </div>
        <ElButton
          v-if="organization.status === 'active'"
          type="danger"
          plain
          @click="draft.status = 'disabled'; save()"
        >
          停用组织
        </ElButton>
        <ElButton
          v-else
          type="success"
          plain
          @click="draft.status = 'active'; save()"
        >
          重新启用
        </ElButton>
      </section>
    </template>
  </section>
</template>
