<script setup lang="ts">
import { Bell, Check, Loading, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, toSafeDisplayError } from '@/api/client'
import { getUnreadNotificationCount, listNotifications, markNotificationRead } from '@/api/warnings'
import type { Notification, NotificationStatus } from '@/api/types'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; 'count-change': [value: number] }>()
const router = useRouter()
const status = ref<NotificationStatus>('unread')
const items = ref<Notification[]>([])
const loading = ref(false)
const errorMessage = ref('')
const requestId = ref<string>()
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const markingId = ref<string | null>(null)

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

function resetError(): void {
  errorMessage.value = ''
  requestId.value = undefined
}

async function load(reset = true): Promise<void> {
  loading.value = true
  resetError()
  if (reset) nextCursor.value = null
  try {
    const page = await listNotifications({ status: status.value, limit: 20, cursor: reset ? undefined : nextCursor.value ?? undefined })
    items.value = reset ? page.items : [...items.value, ...page.items]
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
    const count = await getUnreadNotificationCount()
    emit('count-change', count.unread_count)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
  } finally {
    loading.value = false
  }
}

async function openNotification(item: Notification): Promise<void> {
  if (item.status === 'unread') {
    markingId.value = item.id
    try {
      await markNotificationRead(item.id)
      item.status = 'read'
      const count = await getUnreadNotificationCount()
      emit('count-change', count.unread_count)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        const safe = toSafeDisplayError(error)
        errorMessage.value = safe.message
        requestId.value = safe.requestId
      }
    } finally {
      markingId.value = null
    }
  }
  drawerVisible.value = false
  void router.push(`/warnings/${item.warning_id}`)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

watch([() => props.modelValue, status], ([visible]) => {
  if (visible) void load()
}, { immediate: true })
</script>

<template>
  <ElDrawer
    v-model="drawerVisible"
    title="通知中心"
    direction="rtl"
    size="min(380px, 100vw)"
    aria-label="通知中心"
  >
    <template #header>
      <div class="notification-drawer-heading">
        <span><Bell /> 通知中心</span><ElBadge
          :value="items.filter((item) => item.status === 'unread').length"
          :hidden="items.every((item) => item.status === 'read')"
        />
      </div>
    </template>
    <div class="notification-drawer-content">
      <ElRadioGroup
        v-model="status"
        size="small"
        aria-label="通知状态"
      >
        <ElRadioButton value="unread">
          未读
        </ElRadioButton>
        <ElRadioButton value="read">
          已读
        </ElRadioButton>
      </ElRadioGroup>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      >
        <p
          v-if="requestId"
          class="request-id"
        >
          请求 ID：{{ requestId }}
        </p>
      </ElAlert>
      <ElSkeleton
        v-if="loading && items.length === 0"
        :rows="5"
        animated
      />
      <ElEmpty
        v-else-if="items.length === 0"
        description="暂无通知"
      />
      <div
        v-else
        class="notification-list"
      >
        <button
          v-for="item in items"
          :key="item.id"
          class="notification-item"
          :class="{ 'notification-item--unread': item.status === 'unread' }"
          type="button"
          @click="openNotification(item)"
        >
          <span class="notification-item-icon"><WarningFilled /></span>
          <span class="notification-item-copy"><strong>{{ item.title }}</strong><span>{{ item.body }}</span><small>{{ formatDate(item.created_at) }}</small></span>
          <ElIcon v-if="markingId === item.id">
            <Loading />
          </ElIcon>
          <Check
            v-else-if="item.status === 'read'"
            class="notification-read-icon"
          />
        </button>
      </div>
      <ElButton
        v-if="hasMore"
        class="notification-load-more"
        :icon="Refresh"
        :loading="loading"
        @click="load(false)"
      >
        加载更多
      </ElButton>
    </div>
  </ElDrawer>
</template>
