<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  getPlatformModelConfiguration,
  updatePlatformModelConfiguration,
} from '@/api/organizations'
import type { OrganizationStatus, PlatformModelConfiguration } from '@/api/types'
import PageState from '@/components/PageState.vue'

const configuration = ref<PlatformModelConfiguration | null>(null)
const draft = ref({
  timeout_seconds: 60,
  max_retries: 3,
  usage_tracking_enabled: true,
  status: 'active' as OrganizationStatus,
})
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const conflictMessage = ref('')
const forbidden = ref(false)

const changed = computed(() => {
  if (!configuration.value) return false
  return (
    draft.value.timeout_seconds !== configuration.value.timeout_seconds ||
    draft.value.max_retries !== configuration.value.max_retries ||
    draft.value.usage_tracking_enabled !== configuration.value.usage_tracking_enabled ||
    draft.value.status !== configuration.value.status
  )
})

function applyResource(resource: PlatformModelConfiguration): void {
  configuration.value = resource
  draft.value = {
    timeout_seconds: resource.timeout_seconds,
    max_retries: resource.max_retries,
    usage_tracking_enabled: resource.usage_tracking_enabled,
    status: resource.status,
  }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  try {
    applyResource(await getPlatformModelConfiguration())
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && error.status === 403
  } finally {
    loading.value = false
  }
}

async function confirmDisable(): Promise<boolean> {
  if (draft.value.status !== 'disabled' || configuration.value?.status === 'disabled') return true
  try {
    await ElMessageBox.confirm(
      '停用模型配置会影响后续模型任务。确定继续吗？',
      '确认停用模型配置',
      { type: 'warning', confirmButtonText: '停用配置', cancelButtonText: '取消' },
    )
    return true
  } catch {
    draft.value.status = configuration.value?.status ?? 'active'
    return false
  }
}

async function save(): Promise<void> {
  if (!configuration.value || saving.value || !changed.value) return
  if (!(await confirmDisable())) return
  saving.value = true
  errorMessage.value = ''
  conflictMessage.value = ''
  try {
    const body: {
      timeout_seconds?: number
      max_retries?: number
      usage_tracking_enabled?: boolean
      status?: OrganizationStatus
      version: number
    } = { version: configuration.value.version }
    if (draft.value.timeout_seconds !== configuration.value.timeout_seconds) {
      body.timeout_seconds = draft.value.timeout_seconds
    }
    if (draft.value.max_retries !== configuration.value.max_retries) {
      body.max_retries = draft.value.max_retries
    }
    if (draft.value.usage_tracking_enabled !== configuration.value.usage_tracking_enabled) {
      body.usage_tracking_enabled = draft.value.usage_tracking_enabled
    }
    if (draft.value.status !== configuration.value.status) body.status = draft.value.status
    applyResource(await updatePlatformModelConfiguration(body))
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    if (error instanceof ApiError && error.code === 'RESOURCE_VERSION_CONFLICT') {
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
  <section class="admin-page model-page">
    <div class="page-heading">
      <div>
        <h1>模型配置</h1>
        <p>查看部署模型环境，并调整可由平台管理的运行参数。</p>
      </div>
      <ElButton
        type="primary"
        :loading="saving"
        :disabled="!changed || loading"
        @click="save"
      >
        保存配置
      </ElButton>
    </div>

    <PageState
      v-if="forbidden"
      title="无权访问模型配置"
      description="只有平台管理员可以查看或调整模型运行参数。"
      icon="error"
      :request-id="errorRequestId"
      action-label="重试"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && !configuration"
      title="模型配置加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <template v-else-if="configuration">
      <ElAlert
        v-if="!configuration.secret_configured"
        title="模型环境未配置完成"
        description="部署环境尚未提供模型密钥。此页面不会提供密钥输入框，请由部署配置完成设置。"
        type="error"
        :closable="false"
        show-icon
      />
      <ElAlert
        v-else-if="conflictMessage"
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

      <section class="summary-panel">
        <div class="section-heading">
          <h2>运行环境概览</h2>
          <ElTag
            :type="configuration.status === 'active' ? 'success' : 'info'"
            effect="plain"
          >
            {{ configuration.status === 'active' ? '配置启用' : '配置已停用' }}
          </ElTag>
        </div>
        <dl class="metadata-list">
          <div>
            <dt>服务提供方</dt>
            <dd>{{ configuration.provider }}</dd>
          </div>
          <div>
            <dt>模型标识</dt>
            <dd class="technical-value">
              {{ configuration.model }}
            </dd>
          </div>
          <div>
            <dt>模型来源</dt>
            <dd>
              <ElTag effect="plain">
                部署环境
              </ElTag>
            </dd>
          </div>
          <div>
            <dt>密钥状态</dt>
            <dd :class="configuration.secret_configured ? 'success-text' : 'danger-text'">
              {{ configuration.secret_configured ? '已配置' : '未配置' }}
            </dd>
          </div>
          <div>
            <dt>硬预算</dt>
            <dd>{{ configuration.hard_budget_enabled ? '已启用' : '未启用' }}</dd>
          </div>
          <div>
            <dt>组织覆盖</dt>
            <dd>{{ configuration.organization_overrides_allowed ? '允许' : '不允许' }}</dd>
          </div>
        </dl>
      </section>

      <section class="form-panel">
        <div class="section-heading">
          <div>
            <h2>运行参数</h2>
            <p>模型名称和密钥仅来自部署环境，不能在此页面修改。</p>
          </div>
          <span class="technical-value">v{{ configuration.version }}</span>
        </div>
        <ElForm
          class="admin-form"
          label-position="top"
        >
          <div class="form-row">
            <ElFormItem label="超时秒数">
              <ElInputNumber
                v-model="draft.timeout_seconds"
                :min="1"
                :precision="0"
                controls-position="right"
              />
            </ElFormItem>
            <ElFormItem label="最大重试次数">
              <ElInputNumber
                v-model="draft.max_retries"
                :min="0"
                :precision="0"
                controls-position="right"
              />
            </ElFormItem>
          </div>
          <div class="form-row">
            <ElFormItem label="用量记录">
              <ElSwitch
                v-model="draft.usage_tracking_enabled"
                active-text="启用"
                inactive-text="停用"
              />
            </ElFormItem>
            <ElFormItem label="配置状态">
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
          </div>
        </ElForm>
      </section>

      <section class="danger-panel">
        <div>
          <h2>{{ configuration.status === 'active' ? '停用模型配置' : '重新启用模型配置' }}</h2>
          <p>状态变更只影响平台模型配置的可用性，不会修改部署密钥或模型名称。</p>
        </div>
        <ElButton
          :type="configuration.status === 'active' ? 'danger' : 'success'"
          plain
          @click="draft.status = configuration?.status === 'active' ? 'disabled' : 'active'; save()"
        >
          {{ configuration.status === 'active' ? '停用配置' : '重新启用' }}
        </ElButton>
      </section>
    </template>
  </section>
</template>
