<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { toSafeDisplayError } from '@/api/client'
import { defaultLandingPath, login } from '@/features/auth/session'

const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const canSubmit = computed(() => email.value.trim().length > 0 && password.value.length > 0)

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const session = await login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : defaultLandingPath(session)
    await router.replace(redirect.startsWith('/') ? redirect : '/')
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
      aria-labelledby="login-title"
    >
      <p class="auth-kicker">
        合同智审
      </p>
      <h1 id="login-title">
        登录
      </h1>
      <p class="auth-copy">
        使用您的工作账号继续。
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
          <span>邮箱</span>
          <ElInput
            v-model="email"
            type="email"
            autocomplete="email"
            required
          />
        </label>
        <label>
          <span>密码</span>
          <ElInput
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            show-password
          />
        </label>
        <RouterLink
          class="auth-link"
          to="/password-reset"
        >
          忘记密码
        </RouterLink>
        <ElButton
          native-type="submit"
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit || submitting"
        >
          登录
        </ElButton>
      </form>
    </section>
  </main>
</template>
