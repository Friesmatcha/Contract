<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description: string
    requestId?: string
    icon?: string
    actionLabel?: string
  }>(),
  { requestId: undefined, icon: 'warning', actionLabel: '重试' },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="page-state">
    <ElResult
      :icon="icon"
      :title="title"
      :sub-title="description"
    >
      <template #extra>
        <p
          v-if="requestId"
          class="request-id"
        >
          请求 ID：{{ requestId }}
        </p>
        <ElButton
          type="primary"
          @click="emit('retry')"
        >
          {{ actionLabel }}
        </ElButton>
      </template>
    </ElResult>
  </div>
</template>
