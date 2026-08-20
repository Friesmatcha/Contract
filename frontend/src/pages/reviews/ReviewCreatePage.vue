<script setup lang="ts">
import { ArrowLeft, CircleCheck, VideoPlay } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { toSafeDisplayError } from '@/api/client'
import { getContract } from '@/api/contracts'
import { listClauseTemplates } from '@/api/clauseTemplates'
import { listRiskRuleBundles } from '@/api/riskRules'
import { createReviewTask } from '@/api/reviews'
import type {
  ClauseTemplate,
  Contract,
  ContractFileSummary,
  RiskRuleBundle,
} from '@/api/types'
import PageState from '@/components/PageState.vue'
import {
  currentOrganizationId,
  currentOrganizationMembership,
} from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const contractId = computed(() => String(route.params.contractId ?? ''))
const organizationId = currentOrganizationId
const role = computed(() => currentOrganizationMembership.value?.role)
const canWrite = computed(() => role.value === 'org_admin' || role.value === 'reviewer')

const contract = ref<Contract | null>(null)
const files = ref<ContractFileSummary[]>([])
const rules = ref<RiskRuleBundle[]>([])
const templates = ref<ClauseTemplate[]>([])
const selectedFileId = ref('')
const selectedRuleVersionId = ref('')
const selectedTemplateVersionId = ref('')
const businessScenario = ref('standard')
const activeReviewStatuses = new Set(['pending', 'parsing', 'reviewing', 'pending_review'])
const hasActiveReview = computed(() =>
  Boolean(contract.value?.latest_review && activeReviewStatuses.has(contract.value.latest_review.status)),
)
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const actionError = ref('')
const actionRequestId = ref<string>()

const validFiles = computed(() =>
  files.value.filter(
    (file) =>
      file.scan_status === 'clean' &&
      file.storage_status === 'stored' &&
      Boolean(file.external_model_notice_acknowledged_at),
  ),
)
const selectedFile = computed(() => validFiles.value.find((file) => file.id === selectedFileId.value))
const selectedRule = computed(() =>
  rules.value.find((rule) => rule.id === selectedRuleVersionId.value),
)
const selectedTemplate = computed(() =>
  templates.value.find((template) => template.id === selectedTemplateVersionId.value),
)

function setPageError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
}

function setActionError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  actionError.value = safe.message
  actionRequestId.value = safe.requestId
}

function fileLabel(file: ContractFileSummary): string {
  return `V${file.version_no} · ${file.original_name || '合同文件'}${file.is_current ? ' · 当前' : ''}`
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const loadedContract = await getContract(contractId.value, organizationId.value)
    contract.value = loadedContract
    files.value = loadedContract.files
    selectedFileId.value = validFiles.value.find((file) => file.is_current)?.id || validFiles.value[0]?.id || ''
    const [rulePage, templatePage] = await Promise.all([
      listRiskRuleBundles(organizationId.value, { status: 'active', limit: 100 }),
      loadedContract.declared_type && loadedContract.declared_type !== 'other'
        ? listClauseTemplates(organizationId.value, {
            contract_type: loadedContract.declared_type,
            business_scenario: businessScenario.value,
            status: 'active',
            limit: 100,
          })
        : Promise.resolve({ items: [], next_cursor: null, has_more: false }),
    ])
    rules.value = rulePage.items
    templates.value = templatePage.items
  } catch (error) {
    setPageError(error)
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (
    !selectedFile.value ||
    !canWrite.value ||
    submitting.value ||
    hasActiveReview.value ||
    !contract.value
  ) return
  submitting.value = true
  actionError.value = ''
  const body = {
    contract_file_id: selectedFile.value.id,
    ...(selectedRule.value?.current_published_version_id
      ? { rule_bundle_version_id: selectedRule.value.current_published_version_id }
      : {}),
    ...(selectedTemplate.value?.current_published_version_id
      ? { clause_template_version_id: selectedTemplate.value.current_published_version_id }
      : {}),
    business_scenario: businessScenario.value.trim() || 'standard',
  }
  try {
    const task = await createReviewTask(contract.value.id, body, crypto.randomUUID())
    await router.replace(`/reviews/${task.id}`)
  } catch (error) {
    setActionError(error)
  } finally {
    submitting.value = false
  }
}

function isBlockingApiError(): boolean {
  return errorMessage.value !== '' && !canWrite.value
}

onMounted(() => {
  if (!canWrite.value) {
    errorMessage.value = '当前账户没有创建审核任务的权限。'
    loading.value = false
    return
  }
  void load()
})
</script>

<template>
  <section class="admin-page review-create-page">
    <button
      class="back-link"
      type="button"
      @click="router.push(`/contracts/${contractId}`)"
    >
      <ElIcon><ArrowLeft /></ElIcon> 返回合同详情
    </button>

    <PageState
      v-if="isBlockingApiError()"
      title="无法创建审核"
      :description="errorMessage"
      icon="error"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="errorMessage"
      title="审核创建页加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load"
    />
    <template v-else-if="loading">
      <div class="page-heading">
        <ElSkeleton
          :rows="2"
          animated
        />
      </div>
      <ElSkeleton
        :rows="8"
        animated
      />
    </template>
    <template v-else-if="contract">
      <div class="page-heading">
        <div>
          <div class="technical-value">
            {{ contract.display_no }}
          </div>
          <h1>创建审核任务</h1>
          <p>{{ contract.title }}</p>
        </div>
        <ElTag type="info">
          异步审核
        </ElTag>
      </div>

      <ElAlert
        v-if="actionError"
        :title="actionError"
        :description="actionRequestId ? `请求 ID：${actionRequestId}` : undefined"
        type="error"
        :closable="false"
        show-icon
      />
      <ElAlert
        v-if="hasActiveReview"
        title="合同已有进行中的审核任务"
        description="同一合同同一时间只能有一个活动审核任务。"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <ElButton
            type="primary"
            text
            @click="router.push(`/reviews/${contract.latest_review?.id}`)"
          >
            查看进行中的审核
          </ElButton>
        </template>
      </ElAlert>

      <div class="detail-grid review-create-grid">
        <section class="summary-panel">
          <div class="section-heading">
            <div><h2>输入版本</h2><p>创建后这些输入将固定在任务快照中。</p></div>
          </div>
          <ElForm
            label-position="top"
            class="admin-form"
          >
            <ElFormItem
              label="合同文件版本"
              required
            >
              <ElSelect
                v-model="selectedFileId"
                class="wide-control"
                placeholder="选择已验证文件"
                :disabled="submitting || validFiles.length === 0"
              >
                <ElOption
                  v-for="file in validFiles"
                  :key="file.id"
                  :label="fileLabel(file)"
                  :value="file.id"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="业务场景">
              <ElInput
                v-model="businessScenario"
                maxlength="128"
                :disabled="submitting"
              />
            </ElFormItem>
            <ElFormItem label="风险规则版本">
              <ElSelect
                v-model="selectedRuleVersionId"
                class="wide-control"
                clearable
                placeholder="使用组织默认规则集"
                :disabled="submitting"
              >
                <ElOption
                  v-for="rule in rules"
                  :key="rule.id"
                  :label="`${rule.name}${rule.current_published_version_id ? ' · 已发布' : ' · 无可用发布版本'}`"
                  :value="rule.id"
                  :disabled="!rule.current_published_version_id"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="条款模板版本">
              <ElSelect
                v-model="selectedTemplateVersionId"
                class="wide-control"
                clearable
                placeholder="使用匹配场景默认模板"
                :disabled="submitting"
              >
                <ElOption
                  v-for="template in templates"
                  :key="template.id"
                  :label="`${template.name} · ${template.business_scenario}${template.current_published_version_id ? ' · 已发布' : ''}`"
                  :value="template.id"
                  :disabled="!template.current_published_version_id"
                />
              </ElSelect>
            </ElFormItem>
          </ElForm>
        </section>

        <section class="summary-panel">
          <div class="section-heading">
            <div><h2>创建确认</h2><p>服务端会再次校验文件、版本和权限。</p></div>
          </div>
          <dl class="metadata-list metadata-list-single">
            <div><dt>合同</dt><dd>{{ contract.display_no }} · {{ contract.title }}</dd></div>
            <div><dt>文件</dt><dd>{{ selectedFile ? fileLabel(selectedFile) : '未选择' }}</dd></div>
            <div><dt>文档版本</dt><dd>服务端使用可用解析版本</dd></div>
            <div><dt>风险规则</dt><dd>{{ selectedRule ? selectedRule.name : '组织默认规则集' }}</dd></div>
            <div><dt>条款模板</dt><dd>{{ selectedTemplate ? selectedTemplate.name : '匹配场景默认模板' }}</dd></div>
          </dl>
          <ElAlert
            v-if="validFiles.length === 0"
            title="没有可用的合同文件版本"
            description="请返回合同详情上传并完成安全校验后再创建审核。"
            type="warning"
            :closable="false"
            show-icon
          />
          <div class="page-heading-actions review-actions">
            <ElButton
              :disabled="submitting"
              @click="router.push(`/contracts/${contractId}`)"
            >
              返回
            </ElButton>
            <ElButton
              type="primary"
              :icon="submitting ? undefined : VideoPlay"
              :loading="submitting"
              :disabled="!selectedFile || submitting || hasActiveReview || contract.status === 'archived'"
              @click="submit"
            >
              创建审核任务
            </ElButton>
          </div>
          <p class="form-note">
            <ElIcon><CircleCheck /></ElIcon> 不会在此页面展示模型结果或风险结论。
          </p>
        </section>
      </div>
    </template>
  </section>
</template>
