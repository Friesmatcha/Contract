<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiFetch, toSafeDisplayError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const password = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const completed = ref(false)
const tokenNeedsReissue = ref(false)
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const canSubmit = computed(
  () =>
    token.value.length > 0 &&
    !tokenNeedsReissue.value &&
    password.value.length >= 12 &&
    password.value.length <= 128 &&
    password.value === confirmPassword.value,
)

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
    completed.value = true
  } catch (error) {
    tokenNeedsReissue.value =
      error instanceof ApiError &&
      ['TOKEN_INVALID', 'TOKEN_EXPIRED', 'TOKEN_ALREADY_USED'].includes(error.code)
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
        合同智审
      </p>
      <h1 id="confirm-reset-title">
        设置新密码
      </h1>
      <ElResult
        v-if="completed"
        icon="success"
        title="密码已更新"
        sub-title="请使用新密码登录合同审核系统。"
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
      <ElResult
        v-else-if="!token"
        icon="error"
        title="重置链接无效"
        sub-title="请重新申请密码重置链接。"
      >
        <template #extra>
          <ElButton
            type="primary"
            @click="router.replace('/password-reset')"
          >
            重新申请重置链接
          </ElButton>
        </template>
      </ElResult>
      <template v-else-if="!completed">
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
        <RouterLink
          v-if="tokenNeedsReissue"
          class="auth-link"
          to="/password-reset"
        >
          重新申请重置链接
        </RouterLink>
        <form
          v-if="!tokenNeedsReissue"
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
            :disabled="!canSubmit || submitting"
          >
            保存新密码
          </ElButton>
        </form>
      </template>
    </section>
  </main>
</template>
