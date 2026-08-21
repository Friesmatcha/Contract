<script setup lang="ts">
import { ArrowLeft, Download, Refresh, View } from '@element-plus/icons-vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getReport, reportDownloadUrl } from '@/api/reports'
import type { Report } from '@/api/types'
import PageState from '@/components/PageState.vue'

const route = useRoute()
const router = useRouter()
const reportId = () => String(route.params.reportId ?? '')

const report = ref<Report | null>(null)
const loading = ref(true)
const loadingError = ref('')
const requestId = ref<string>()
const forbidden = ref(false)
let pollingTimer: ReturnType<typeof setTimeout> | undefined
let pollingDelay = 1500

const statusLabels: Record<Report['status'], string> = {
  generating: '正在生成',
  ready: '已就绪',
  failed: '生成失败',
  expired: '已过期',
}

function statusType(status: Report['status']): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'ready') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'expired') return 'warning'
  return 'info'
}

function formatLabel(format: Report['format']): string {
  return format === 'html' ? 'HTML' : 'PDF'
}

function clearPolling(): void {
  if (pollingTimer !== undefined) {
    clearTimeout(pollingTimer)
    pollingTimer = undefined
  }
}

function schedulePolling(): void {
  clearPolling()
  if (report.value?.status !== 'generating') return
  pollingTimer = setTimeout(() => {
    void load(false)
  }, pollingDelay)
  pollingDelay = Math.min(pollingDelay * 1.5, 5000)
}

function setError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  loadingError.value = safe.message
  requestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(initial = true): Promise<void> {
  if (initial) loading.value = true
  loadingError.value = ''
  forbidden.value = false
  try {
    report.value = await getReport(reportId())
    pollingDelay = 1500
    schedulePolling()
  } catch (error) {
    clearPolling()
    setError(error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(clearPolling)
</script>

<template>
  <section class="admin-page report-page">
    <button class="back-link" type="button" @click="router.back()">
      <ElIcon><ArrowLeft /></ElIcon> 返回上一页
    </button>

    <PageState
      v-if="forbidden"
      title="无法访问报告"
      :description="loadingError || '报告不存在或当前账户没有查看权限。'"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <PageState
      v-else-if="loadingError && !report"
      title="报告加载失败"
      :description="loadingError"
      icon="error"
      :request-id="requestId"
      @retry="load"
    />
    <template v-else-if="loading && !report">
      <div class="page-heading"><ElSkeleton :rows="2" animated /></div>
      <ElSkeleton :rows="12" animated />
    </template>
    <template v-else-if="report">
      <div class="page-heading report-heading">
        <div>
          <div class="technical-value">{{ report.display_no }}</div>
          <h1>合同风险分析报告</h1>
          <p>{{ formatLabel(report.format) }} · 模板 {{ report.template_version }}</p>
        </div>
        <div class="report-heading-actions">
          <ElTag :type="statusType(report.status)">{{ statusLabels[report.status] }}</ElTag>
          <a
            v-if="report.download_available"
            class="report-action-button"
            :href="reportDownloadUrl(report.id)"
            :download="`${report.display_no}.${report.format}`"
          ><ElIcon><Download /></ElIcon> 下载{{ formatLabel(report.format) }}</a>
        </div>
      </div>

      <ElAlert
        v-if="report.status === 'generating'"
        title="报告正在生成"
        description="报告基于创建时冻结的审核结果生成，完成后本页会自动更新。"
        type="info"
        :closable="false"
        show-icon
      />
      <ElAlert
        v-else-if="report.status === 'failed'"
        title="报告生成失败"
        description="审核结果没有受到影响，请回到审核结果页使用新的请求重新生成。"
        type="error"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="report-state-actions">
            <span v-if="report.error_code" class="technical-value">{{ report.error_code }}</span>
            <ElButton :icon="Refresh" @click="router.push(`/reviews/${report.review_task_id}/results`)">重新生成</ElButton>
          </div>
        </template>
      </ElAlert>
      <ElAlert
        v-else-if="report.status === 'expired'"
        title="报告已过期"
        description="报告文件已超过组织保留期，请回到审核结果页创建新的不可变报告。"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default><ElButton :icon="Refresh" @click="router.push(`/reviews/${report.review_task_id}/results`)">重新生成</ElButton></template>
      </ElAlert>

      <div class="report-metadata-grid">
        <div class="summary-panel"><span class="result-label">报告 ID</span><strong class="technical-value">{{ report.id }}</strong></div>
        <div class="summary-panel"><span class="result-label">审核任务 ID</span><strong class="technical-value">{{ report.review_task_id }}</strong></div>
        <div class="summary-panel"><span class="result-label">生成时间</span><strong>{{ report.generated_at || '处理中' }}</strong></div>
        <div class="summary-panel"><span class="result-label">有效期至</span><strong>{{ report.expires_at || '生成完成后计算' }}</strong></div>
      </div>

      <ElAlert
        title="参考声明"
        description="本报告由智能分析引擎生成，旨在辅助专业人员进行风险识别，不能替代独立法律意见。请结合实际业务场景与人工复核进行最终决策。"
        type="info"
        :closable="false"
        show-icon
      />

      <section v-if="report.status === 'ready' && report.format === 'html'" class="summary-panel report-preview-panel">
        <div class="section-heading">
          <div><h2>内容预览</h2><p>预览使用同一份已生成的 HTML 文件。</p></div>
          <ElIcon><View /></ElIcon>
        </div>
        <iframe
          class="report-preview-frame"
          :src="reportDownloadUrl(report.id, 'inline')"
          title="报告 HTML 预览"
          sandbox=""
        />
      </section>
    </template>
  </section>
</template>
