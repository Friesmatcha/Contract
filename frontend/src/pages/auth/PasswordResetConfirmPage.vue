<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { apiFetch, toSafeDisplayError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const password = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))

async function submit(): Promise<void> {
  if (submitting.value) return
  if (!token.value) {
    errorMessage.value = '重置链接无效。'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    await apiFetch<void>('/api/v1/auth/password-reset/confirm', {
      method: 'POST',
      body: JSON.stringify({ token: token.value, new_password: password.value }),
    })
    await router.replace('/login')
  } catch (error) {
    errorMessage.value = toSafeDisplayError(error).message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section
      class="auth-panel"
      aria-labelledby="confirm-reset-title"
    >
      <p class="auth-kicker">
        CONTRACT REVIEW
      </p>
      <h1 id="confirm-reset-title">
        设置新密码
      </h1>
      <p class="auth-copy">
        密码长度为 12 到 128 个字符。
      </p>
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />
      <form
        class="auth-form"
        @submit.prevent="submit"
      >
        <label>
          <span>新密码</span>
          <ElInput
            v-model="password"
            type="password"
            autocomplete="new-password"
            required
            show-password
          />
        </label>
        <label>
          <span>确认新密码</span>
          <ElInput
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            required
            show-password
          />
        </label>
        <ElButton
          native-type="submit"
          type="primary"
          :loading="submitting"
        >
          保存新密码
        </ElButton>
      </form>
    </section>
  </main>
</template>
