<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { logout, sessionState } from '@/features/auth/session'

const router = useRouter()
const submitting = ref(false)

async function signOut(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  try {
    await logout()
    await router.replace('/login')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="session-page">
    <section
      class="session-panel"
      aria-labelledby="session-title"
    >
      <p class="auth-kicker">
        CONTRACT REVIEW
      </p>
      <h1 id="session-title">
        会话已建立
      </h1>
      <p
        v-if="sessionState.current"
        class="auth-copy"
      >
        {{ sessionState.current.user.display_name }}
      </p>
      <ElButton
        type="default"
        :loading="submitting"
        @click="signOut"
      >
        退出登录
      </ElButton>
    </section>
  </main>
</template>
