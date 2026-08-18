<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiFetch, toSafeDisplayError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const displayName = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const accepted = ref(false)
const tokenRejected = ref(false)
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const canSubmit = computed(() => token.value.length > 0 && !tokenRejected.value)

async function submit(): Promise<void> {
  if (submitting.value) return
  if (!token.value) {
    errorMessage.value = '邀请链接无效。'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    await apiFetch('/api/v1/auth/invitations/accept', {
      method: 'POST',
      body: JSON.stringify({
        token: token.value,
        display_name: displayName.value || undefined,
        password: password.value || undefined,
      }),
    })
    accepted.value = true
  } catch (error) {
    tokenRejected.value =
      error instanceof ApiError && ['TOKEN_INVALID', 'TOKEN_EXPIRED'].includes(error.code)
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
      aria-labelledby="invite-title"
    >
      <p class="auth-kicker">
        合同智审
      </p>
      <h1 id="invite-title">
        接受邀请
      </h1>
      <ElResult
        v-if="accepted"
        icon="success"
        title="邀请已接受"
        sub-title="现在可以使用组织账号登录。"
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
        title="邀请链接无效"
        sub-title="请联系组织管理员重新获取邀请链接。"
      />
      <template v-else-if="!accepted">
        <p class="auth-copy">
          新用户请填写展示名与密码；已有账号可直接提交。
        </p>
        <ElAlert
          v-if="errorMessage"
          :title="errorMessage"
          type="error"
          :closable="false"
          show-icon
        />
        <form
          v-if="!tokenRejected"
          class="auth-form"
          @submit.prevent="submit"
        >
          <label>
            <span>展示名</span>
            <ElInput
              v-model="displayName"
              autocomplete="name"
            />
          </label>
          <label>
            <span>密码</span>
            <ElInput
              v-model="password"
              type="password"
              autocomplete="new-password"
              show-password
            />
          </label>
          <ElButton
            native-type="submit"
            type="primary"
            :loading="submitting"
            :disabled="!canSubmit || submitting"
          >
            接受邀请
          </ElButton>
        </form>
      </template>
    </section>
  </main>
</template>
