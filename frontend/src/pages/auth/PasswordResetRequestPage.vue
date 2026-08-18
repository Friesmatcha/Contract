<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiFetch, toSafeDisplayError } from '@/api/client'

const email = ref('')
const router = useRouter()
const submitting = ref(false)
const errorMessage = ref('')
const accepted = ref(false)
const canSubmit = computed(() => email.value.trim().length > 0)

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
        合同智审
      </p>
      <h1 id="reset-title">
        重置密码
      </h1>
      <p class="auth-copy">
        输入工作邮箱后，系统会继续处理重置请求。
      </p>
      <ElResult
        v-if="accepted"
        icon="success"
        title="请求已受理"
        sub-title="如果账号存在，系统将继续处理密码重置请求。"
      >
        <template #extra>
          <ElButton
            type="primary"
            @click="router.replace('/login')"
          >
            返回登录
          </ElButton>
        </template>
      </ElResult>
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
          :disabled="!canSubmit || submitting"
        >
          发送请求
        </ElButton>
      </form>
    </section>
  </main>
</template>
