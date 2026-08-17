<script setup lang="ts">
import { ref } from 'vue'

import { apiFetch, toSafeDisplayError } from '@/api/client'

const email = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const accepted = ref(false)

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await apiFetch('/api/v1/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ email: email.value }),
    })
    accepted.value = true
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
      aria-labelledby="reset-title"
    >
      <p class="auth-kicker">
        CONTRACT REVIEW
      </p>
      <h1 id="reset-title">
        重置密码
      </h1>
      <p class="auth-copy">
        输入工作邮箱后，系统会继续处理重置请求。
      </p>
      <ElAlert
        v-if="accepted"
        title="如果账号存在，系统将继续处理密码重置请求。"
        type="success"
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
      <form
        v-if="!accepted"
        class="auth-form"
        @submit.prevent="submit"
      >
        <label>
          <span>邮箱</span>
          <ElInput
            v-model="email"
            type="email"
            autocomplete="email"
            required
          />
        </label>
        <ElButton
          native-type="submit"
          type="primary"
          :loading="submitting"
        >
          发送请求
        </ElButton>
      </form>
      <RouterLink
        class="auth-link"
        to="/login"
      >
        返回登录
      </RouterLink>
    </section>
  </main>
</template>
