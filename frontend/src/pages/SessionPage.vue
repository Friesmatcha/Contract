<script setup lang="ts">
import { computed } from 'vue'

import {
  activeOrganizationMemberships,
  currentOrganizationMembership,
  sessionState,
} from '@/features/auth/session'

const session = computed(() => sessionState.current)
const membership = currentOrganizationMembership
const needsOrganizationSelection = computed(
  () => !membership.value && activeOrganizationMemberships.value.length > 1,
)
</script>

<template>
  <section class="workspace-home">
    <div class="page-heading">
      <div>
        <h1 id="session-title">
          会话已建立
        </h1>
        <p>已恢复当前账户的可用工作区。</p>
      </div>
    </div>
    <ElAlert
      v-if="session?.user.is_platform_admin"
      title="平台管理员可从左侧进入组织与模型配置。"
      type="info"
      :closable="false"
      show-icon
    />
    <section
      v-else-if="membership"
      class="summary-panel"
      aria-label="当前组织"
    >
      <h2>{{ membership.organization_name }}</h2>
      <dl class="metadata-list">
        <div>
          <dt>当前角色</dt>
          <dd>{{ membership.role }}</dd>
        </div>
        <div>
          <dt>组织 ID</dt>
          <dd class="technical-value">
            {{ membership.organization_id }}
          </dd>
        </div>
      </dl>
    </section>
    <ElResult
      v-else-if="needsOrganizationSelection"
      icon="info"
      title="请选择当前组织"
      sub-title="请在左侧组织选择器中选择要操作的组织。"
    />
    <ElResult
      v-else
      icon="info"
      title="当前账户尚无可用组织"
      sub-title="请联系平台管理员获取组织访问权限。"
    />
  </section>
</template>
