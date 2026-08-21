<script setup lang="ts">
import { Refresh, Search } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getFeedbackSummary } from '@/api/feedback'
import type { ContractCategory, FeedbackSummary } from '@/api/types'
import { currentOrganizationId, currentOrganizationMembership } from '@/features/auth/session'
import PageState from '@/components/PageState.vue'

const summary = ref<FeedbackSummary | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
const contractType = ref<ContractCategory | ''>('')
const ruleBundleVersionId = ref('')
const modelVersion = ref('')
const createdFrom = ref('')
const createdTo = ref('')

const isAdmin = computed(() => currentOrganizationMembership.value?.role === 'org_admin')
const labels: Record<keyof FeedbackSummary['counts'], string> = {
  correct: '正确',
  incorrect: '错误',
  modified: '修改',
  ignored: '忽略',
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  forbidden.value = false
  try {
      summary.value = await getFeedbackSummary({
        organizationId: currentOrganizationId.value || undefined,
        contractType: contractType.value || undefined,
        ruleBundleVersionId: ruleBundleVersionId.value.trim() || undefined,
        modelVersion: modelVersion.value.trim() || undefined,
      createdFrom: createdFrom.value || undefined,
      createdTo: createdTo.value || undefined,
    })
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
  contractType.value = ''
  ruleBundleVersionId.value = ''
  modelVersion.value = ''
  createdFrom.value = ''
  createdTo.value = ''
  void load()
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page feedback-summary-page">
    <PageState
      v-if="forbidden"
      title="无法查看反馈统计"
      :description="errorMessage || '当前账户没有组织管理员权限。'"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <PageState
      v-else-if="errorMessage && !summary"
      title="反馈统计加载失败"
      :description="errorMessage"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <template v-else>
      <div class="page-heading">
        <div>
          <div class="technical-value">ADMIN-003</div>
          <h1>反馈统计</h1>
          <p>按当前组织的审核任务快照聚合人工反馈。</p>
        </div>
      </div>
      <ElAlert
        v-if="errorMessage && summary"
        title="筛选未完成"
        :description="errorMessage"
        type="warning"
        :closable="false"
        show-icon
      />
      <ElSkeleton v-if="loading && !summary" :rows="8" animated />
      <template v-else>
        <section class="filter-panel feedback-summary-filters" aria-label="反馈统计筛选">
          <ElSelect v-model="contractType" clearable placeholder="合同类型" aria-label="合同类型">
            <ElOption label="采购合同" value="purchase" />
            <ElOption label="销售合同" value="sales" />
            <ElOption label="保密协议" value="nda" />
            <ElOption label="服务外包" value="outsourcing" />
            <ElOption label="劳动合同" value="employment" />
            <ElOption label="其他合同" value="other" />
          </ElSelect>
          <ElInput v-model="ruleBundleVersionId" placeholder="规则版本 ID" aria-label="规则版本 ID" clearable />
          <ElInput v-model="modelVersion" placeholder="模型版本" aria-label="模型版本" clearable />
          <ElInput v-model="createdFrom" type="datetime-local" aria-label="开始时间" />
          <ElInput v-model="createdTo" type="datetime-local" aria-label="结束时间" />
          <ElButton type="primary" :icon="Search" :loading="loading" :disabled="!isAdmin" @click="load">筛选</ElButton>
          <ElButton :icon="Refresh" :disabled="loading" @click="reset">重置</ElButton>
        </section>
        <template v-if="summary">
          <section class="summary-panel feedback-count-panel" aria-label="反馈总数">
            <div v-for="(label, key) in labels" :key="key" class="feedback-count">
              <span class="result-label">{{ label }}</span>
              <strong>{{ summary.counts[key] }}</strong>
            </div>
          </section>
          <section class="table-panel feedback-risk-panel">
            <div class="section-heading"><div><h2>风险类型分布</h2><p>仅统计风险发现 subject 的反馈。</p></div></div>
            <ElEmpty v-if="summary.by_risk_type.length === 0" description="当前筛选暂无风险反馈" />
            <div v-else class="review-result-table-scroll">
              <table class="review-result-table">
                <thead><tr><th>风险类型</th><th>正确</th><th>错误</th><th>修改</th><th>忽略</th></tr></thead>
                <tbody>
                  <tr v-for="item in summary.by_risk_type" :key="item.risk_type">
                    <td class="technical-value">{{ item.risk_type }}</td><td>{{ item.correct }}</td><td>{{ item.incorrect }}</td><td>{{ item.modified }}</td><td>{{ item.ignored }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </template>
    </template>
  </section>
</template>
