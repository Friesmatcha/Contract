<script setup lang="ts">
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import {
  documentFileDownloadUrl,
  getDocumentBlocks,
  getDocumentPage,
} from '@/api/documents'
import type { DocumentBlock, DocumentBlocksResponse, DocumentPageResponse } from '@/api/types'
import PageState from '@/components/PageState.vue'
import { currentOrganizationId } from '@/features/auth/session'

const route = useRoute()
const router = useRouter()
const documentVersionId = computed(() => String(route.params.documentVersionId ?? ''))
const organizationId = currentOrganizationId
const pageFromRoute = computed(() => {
  const value = Number(route.query.page ?? 1)
  return Number.isInteger(value) && value > 0 ? value : 1
})
const selectedSourceSpanId = computed(() => String(route.query.source_span_id || ''))

const loading = ref(true)
const errorMessage = ref('')
const errorRequestId = ref<string>()
const forbidden = ref(false)
const page = ref<DocumentPageResponse | null>(null)
const logicalBlocks = ref<DocumentBlocksResponse | null>(null)
const requestedPage = ref(pageFromRoute.value)

const documentKind = computed(() => page.value?.document_kind || logicalBlocks.value?.document_kind)
const blocks = computed<DocumentBlock[]>(() => page.value?.blocks || logicalBlocks.value?.blocks || [])
const isPhysicalPage = computed(() => documentKind.value === 'pdf' || documentKind.value === 'image')
const pageCount = computed(() => page.value?.page_count || logicalBlocks.value?.page_count || 0)
const imageUrl = computed(() =>
  page.value?.image_file_id ? documentFileDownloadUrl(page.value.image_file_id) : '',
)

function clearState(): void {
  errorMessage.value = ''
  errorRequestId.value = undefined
  forbidden.value = false
  page.value = null
  logicalBlocks.value = null
}

function setError(error: unknown): void {
  const safe = toSafeDisplayError(error)
  errorMessage.value = safe.message
  errorRequestId.value = safe.requestId
  forbidden.value = error instanceof ApiError && (error.status === 403 || error.status === 404)
}

async function load(): Promise<void> {
  loading.value = true
  clearState()
  try {
    page.value = await getDocumentPage(
      documentVersionId.value,
      requestedPage.value,
      organizationId.value,
    )
  } catch (error) {
    if (
      error instanceof ApiError &&
      ['DOCUMENT_NOT_FOUND', 'DOCUMENT_OR_PAGE_NOT_FOUND'].includes(error.code)
    ) {
      try {
        logicalBlocks.value = await getDocumentBlocks(documentVersionId.value, organizationId.value)
      } catch (blocksError) {
        setError(blocksError)
      }
    } else {
      setError(error)
    }
  } finally {
    loading.value = false
  }
}

function changePage(): void {
  if (!isPhysicalPage.value || requestedPage.value < 1 || requestedPage.value > pageCount.value) return
  void router.replace({ query: { ...route.query, page: String(requestedPage.value) } })
}

function sourceLabel(block: DocumentBlock): string {
  if (block.table_path) return block.table_path
  if (block.paragraph_no !== null) return `段落 ${block.paragraph_no}`
  return block.page_no ? `第 ${block.page_no} 页` : '逻辑块'
}

function blockIsHighlighted(block: DocumentBlock): boolean {
  if (!selectedSourceSpanId.value) return block.source_spans.length > 0
  return block.source_spans.some((span) => span.source_span_id === selectedSourceSpanId.value)
}

function ocrLabel(status: string): string {
  const labels: Record<string, string> = {
    not_required: '无需 OCR',
    completed: 'OCR 完成',
    low_confidence: '低置信度',
    blank: '空白页',
    failed: 'OCR 失败',
  }
  return labels[status] || status
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push('/contracts')
}

onMounted(() => {
  void load()
})

watch(pageFromRoute, (value) => {
  if (value === requestedPage.value) return
  requestedPage.value = value
  void load()
})
</script>

<template>
  <section class="document-preview-page">
    <div class="document-toolbar">
      <ElButton
        :icon="ArrowLeft"
        text
        @click="goBack"
      >
        返回来源
      </ElButton>
      <div class="document-identity">
        <span class="technical-value">{{ documentVersionId }}</span>
        <ElTag
          v-if="documentKind"
          type="info"
        >
          {{ documentKind.toUpperCase() }}
        </ElTag>
      </div>
      <div
        v-if="isPhysicalPage"
        class="document-page-control"
      >
        <ElInputNumber
          v-model="requestedPage"
          :min="1"
          :max="pageCount || 1"
          controls-position="right"
          aria-label="页码"
          @change="changePage"
        />
        <span> / {{ pageCount }} 页</span>
      </div>
    </div>

    <PageState
      v-if="forbidden"
      title="无法访问文档"
      :description="errorMessage || '文档不存在或当前账户没有查看权限。'"
      :request-id="errorRequestId"
      @retry="load"
    />
    <PageState
      v-else-if="errorMessage"
      title="文档预览加载失败"
      :description="errorMessage"
      :request-id="errorRequestId"
      @retry="load"
    />
    <div
      v-else-if="loading"
      class="document-preview-loading"
    >
      <ElSkeleton
        :rows="12"
        animated
      />
    </div>
    <div
      v-else-if="page || logicalBlocks"
      class="document-workspace"
    >
      <main class="document-surface">
        <template v-if="page">
          <img
            v-if="imageUrl"
            class="document-page-image"
            :src="imageUrl"
            alt="合同页面预览"
          >
          <div class="document-page-text">
            <p
              v-for="block in blocks"
              :key="block.id"
              class="document-block"
              :class="{ 'document-block-highlighted': blockIsHighlighted(block) }"
            >
              {{ block.text }}
            </p>
          </div>
        </template>
        <template v-else>
          <div class="docx-block-list">
            <article
              v-for="block in blocks"
              :key="block.id"
              class="docx-block"
              :class="{ 'document-block-highlighted': blockIsHighlighted(block) }"
            >
              <div class="docx-block-meta">
                <span>{{ sourceLabel(block) }}</span>
                <span class="technical-value">#{{ block.order_no }}</span>
              </div>
              <p>{{ block.text }}</p>
            </article>
          </div>
        </template>
      </main>
      <aside class="document-context-panel">
        <div class="section-heading">
          <div>
            <h2>定位上下文</h2>
            <p>{{ selectedSourceSpanId ? '已定位到结果证据。' : '每个逻辑块保留原始顺序和证据定位。' }}</p>
          </div>
          <ElButton
            :icon="Refresh"
            text
            aria-label="刷新文档"
            title="刷新文档"
            @click="load"
          />
        </div>
        <ElAlert
          v-if="page?.ocr_status && page.ocr_status !== 'not_required'"
          :title="ocrLabel(page.ocr_status)"
          :description="page.error_message || (page.ocr_confidence !== null ? `置信度 ${(page.ocr_confidence * 100).toFixed(1)}%` : undefined)"
          :type="page.ocr_status === 'completed' ? 'success' : 'warning'"
          :closable="false"
          show-icon
        />
        <ElEmpty
          v-if="blocks.length === 0"
          description="暂无可显示的逻辑块"
        />
        <div
          v-for="block in blocks"
          :key="`context-${block.id}`"
          class="document-context-item"
        >
          <div class="document-context-item-heading">
            <ElTag size="small">
              {{ block.block_type }}
            </ElTag>
            <span>{{ sourceLabel(block) }}</span>
          </div>
          <p>{{ block.text }}</p>
          <blockquote v-if="block.source_spans[0]">
            {{ block.source_spans[0].quote }}
          </blockquote>
        </div>
      </aside>
    </div>
  </section>
</template>
