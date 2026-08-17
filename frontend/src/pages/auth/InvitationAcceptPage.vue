<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { apiFetch, toSafeDisplayError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const displayName = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))

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
      aria-labelledby="invite-title"
    >
      <p class="auth-kicker">
        CONTRACT REVIEW
      </p>
      <h1 id="invite-title">
        接受邀请
      </h1>
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
        >
          接受邀请
        </ElButton>
      </form>
    </section>
  </main>
</template>
