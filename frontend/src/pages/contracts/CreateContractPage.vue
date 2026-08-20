<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { toSafeDisplayError } from '@/api/client'
import { createContract } from '@/api/contracts'
import type { ContractType } from '@/api/types'
import { currentOrganizationId } from '@/features/auth/session'

const router = useRouter()
const organizationId = currentOrganizationId
const title = ref('')
const declaredType = ref<ContractType | ''>('')
const submitting = ref(false)
const errorMessage = ref('')
const requestId = ref<string>()

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `contract-create-${Date.now()}`
}

async function submit(): Promise<void> {
  if (!title.value.trim() || submitting.value || !organizationId.value) {
    errorMessage.value = title.value.trim() ? '当前没有可用组织。' : '请输入合同名称。'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  requestId.value = undefined
  try {
    const contract = await createContract(
      organizationId.value,
      { title: title.value.trim(), declared_type: declaredType.value || undefined },
      newIdempotencyKey(),
    )
    await router.replace(`/contracts/${contract.id}`)
  } catch (error) {
    const safe = toSafeDisplayError(error)
    errorMessage.value = safe.message
    requestId.value = safe.requestId
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="admin-page contract-create-page">
    <button
      class="back-link"
      type="button"
      @click="router.push('/contracts')"
    >
      返回合同目录
    </button>
    <div class="page-heading">
      <div>
        <h1>创建合同</h1>
        <p>先建立合同元数据，文件上传和审核在后续步骤完成。</p>
      </div>
    </div>
    <section class="form-panel compact-form-panel">
      <ElAlert
        v-if="errorMessage"
        :title="errorMessage"
        :description="requestId ? `请求 ID：${requestId}` : undefined"
        type="error"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <ElForm
        label-position="top"
        class="admin-form"
        @submit.prevent="submit"
      >
        <ElFormItem
          label="合同名称"
          required
        >
          <ElInput
            v-model="title"
            maxlength="500"
            show-word-limit
            aria-label="合同名称"
            placeholder="例如：2026 年供应商采购合同"
          />
        </ElFormItem>
        <ElFormItem label="声明合同类型">
          <ElSelect
            v-model="declaredType"
            clearable
            aria-label="声明合同类型"
            placeholder="可选"
          >
            <ElOption
              label="采购"
              value="purchase"
            />
            <ElOption
              label="销售"
              value="sales"
            />
            <ElOption
              label="保密协议"
              value="nda"
            />
            <ElOption
              label="服务外包"
              value="outsourcing"
            />
            <ElOption
              label="劳动"
              value="employment"
            />
            <ElOption
              label="其他/待确认"
              value="other"
            />
          </ElSelect>
        </ElFormItem>
        <p class="form-hint">
          创建后可在合同详情中继续上传文件。组织归属由当前会话确定。
        </p>
        <div class="page-heading-actions">
          <ElButton @click="router.push('/contracts')">
            取消
          </ElButton>
          <ElButton
            type="primary"
            :loading="submitting"
            @click="submit"
          >
            创建合同
          </ElButton>
        </div>
      </ElForm>
    </section>
  </section>
</template>
