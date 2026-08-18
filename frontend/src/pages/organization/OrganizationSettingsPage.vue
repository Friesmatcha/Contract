<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  getOrganizationProfile,
  getOrganizationSettings,
  updateOrganizationSettings,
} from '@/api/organizations'
import type { OrganizationProfile, OrganizationSettings } from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const organizationId = computed(() => String(route.params.organizationId ?? ''))
const profile = ref<OrganizationProfile | null>(null)
const settings = ref<OrganizationSettings | null>(null)
const draft = ref<OrganizationSettings | null>(null)
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string | undefined>()
const conflictMessage = ref('')
const forbidden = ref(false)

const changed = computed(() => {
  if (!settings.value || !draft.value) return false
  return Object.keys(settings.value).some((key) => {
    const field = key as keyof OrganizationSettings
    return field !== 'version' && draft.value?.[field] !== settings.value?.[field]
  })
})

function applyResource(resource: OrganizationSettings): void {
  settings.value = resource
  draft.value = { ...resource }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  try {
    const loadedProfile = await getOrganizationProfile(organizationId.value)
    profile.value = loadedProfile
    if (loadedProfile.my_role !== 'org_admin') {
      forbidden.value = true
      errorMessage.value = '只有组织管理员可以维护组织设置。'
      return
    }
    applyResource(await getOrganizationSettings(organizationId.value))
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    errorRequestId.value = safe.requestId
    forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
  } finally {
    loading.value = false
  }
}

async function confirmRetentionChange(): Promise<boolean> {
  if (!settings.value || !draft.value || draft.value.retention_days === settings.value.retention_days) {
    return true
  }
  try {
    await ElMessageBox.confirm(
      '调整保留天数可能影响未来的数据清理范围。确定保存吗？',
      '确认调整保留策略',
      { type: 'warning', confirmButtonText: '保存设置', cancelButtonText: '取消' },
    )
    return true
  } catch {
    if (draft.value && settings.value) draft.value.retention_days = settings.value.retention_days
    return false
  }
}

async function save(): Promise<void> {
  if (!settings.value || !draft.value || saving.value || !changed.value) return
  if (!(await confirmRetentionChange())) return
  saving.value = true
  errorMessage.value = ''
  conflictMessage.value = ''
  try {
    const body: Record<string, number | boolean | string> & { version: number } = {
      version: settings.value.version,
    }
    const editableFields: Array<keyof OrganizationSettings> = [
      'file_size_limit_bytes',
      'page_limit',
      'concurrent_review_limit',
      'warn_on_medium_risk',
      'ocr_low_confidence_threshold',
      'retention_days',
      'report_watermark',
    ]
    for (const field of editableFields) {
      if (draft.value[field] !== settings.value[field]) body[field] = draft.value[field] as never
    }
    applyResource(await updateOrganizationSettings(organizationId.value, body))
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

function reset(): void {
  if (settings.value) draft.value = { ...settings.value }
  errorMessage.value = ''
  conflictMessage.value = ''
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page organization-settings-page">
    <div class="page-heading">
      <div>
        <h1>组织设置</h1>
        <p v-if="profile">
          {{ profile.name }} · 仅组织管理员可编辑
        </p>
      </div>
      <div class="page-heading-actions">
        <ElButton
          :disabled="!changed || saving"
          @click="reset"
        >
          放弃修改
        </ElButton>
        <ElButton
          type="primary"
          :loading="saving"
          :disabled="!changed || loading"
          @click="save"
        >
          保存设置
        </ElButton>
      </div>
    </div>

    <PageState
      v-if="forbidden"
      title="无法访问组织设置"
      :description="errorMessage || '当前账户没有组织管理员权限。'"
      icon="error"
      :request-id="errorRequestId"
      action-label="重试"
      @retry="load()"
    />
    <PageState
      v-else-if="errorMessage && !settings"
      title="组织设置加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load()"
    />
    <template v-else-if="settings && draft">
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
      <ElAlert
        title="模型密钥和底层模型名称由平台统一维护，本页只展示组织级非秘密设置。"
        type="info"
        :closable="false"
        show-icon
      />

      <div class="settings-grid">
        <section class="form-panel">
          <div class="section-heading">
            <h2>文件与并发</h2>
          </div>
          <ElForm
            class="admin-form"
            label-position="top"
          >
            <ElFormItem label="文件大小上限（bytes）">
              <ElInputNumber
                v-model="draft.file_size_limit_bytes"
                :min="1"
                :precision="0"
                controls-position="right"
              />
            </ElFormItem>
            <ElFormItem label="页数上限">
              <ElInputNumber
                v-model="draft.page_limit"
                :min="1"
                :precision="0"
                controls-position="right"
              />
            </ElFormItem>
            <ElFormItem label="并发审核上限">
              <ElInputNumber
                v-model="draft.concurrent_review_limit"
                :min="1"
                :precision="0"
                controls-position="right"
              />
            </ElFormItem>
          </ElForm>
        </section>
        <section class="form-panel">
          <div class="section-heading">
            <h2>预警与 OCR</h2>
          </div>
          <ElForm
            class="admin-form"
            label-position="top"
          >
            <ElFormItem label="中风险生成预警">
              <ElSwitch
                v-model="draft.warn_on_medium_risk"
                aria-label="中风险生成预警"
                active-text="启用"
                inactive-text="停用"
              />
            </ElFormItem>
            <ElFormItem label="OCR 低置信阈值（0-1）">
              <ElInputNumber
                v-model="draft.ocr_low_confidence_threshold"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                controls-position="right"
              />
            </ElFormItem>
          </ElForm>
        </section>
        <section class="form-panel settings-wide-panel">
          <div class="section-heading">
            <h2>保留与报告</h2>
            <span class="technical-value">v{{ settings.version }}</span>
          </div>
          <ElForm
            class="admin-form"
            label-position="top"
          >
            <div class="form-row">
              <ElFormItem label="数据保留天数">
                <ElInputNumber
                  v-model="draft.retention_days"
                  :min="0"
                  :precision="0"
                  controls-position="right"
                />
              </ElFormItem>
              <ElFormItem label="报告水印">
                <ElInput
                  v-model="draft.report_watermark"
                  maxlength="255"
                  show-word-limit
                />
              </ElFormItem>
            </div>
          </ElForm>
        </section>
      </div>
    </template>
  </section>
</template>
