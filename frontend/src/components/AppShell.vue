<script setup lang="ts">
import {
  ArrowDown,
  FolderOpened,
  Key,
  OfficeBuilding,
  Operation,
  Setting,
  SwitchButton,
  UserFilled,
  User,
} from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { logout, sessionState } from '@/features/auth/session'

const router = useRouter()
const route = useRoute()
const signingOut = ref(false)

const session = computed(() => sessionState.current)
const isPlatformAdmin = computed(() => session.value?.user.is_platform_admin ?? false)
const organizationId = computed(() => {
  const routeOrganizationId = route.params.organizationId
  if (typeof routeOrganizationId === 'string') return routeOrganizationId
  return session.value?.memberships[0]?.organization_id
})
const currentMembership = computed(() =>
  session.value?.memberships.find((membership) => membership.organization_id === organizationId.value),
)
const contextTitle = computed(() => {
  if (isPlatformAdmin.value) return '平台工作区'
  return currentMembership.value?.organization_name ?? '组织工作区'
})
const contextRole = computed(() => {
  if (isPlatformAdmin.value) return '平台管理员'
  const role = currentMembership.value?.role
  if (role === 'org_admin') return '组织管理员'
  if (role === 'reviewer') return '审核员'
  if (role === 'viewer') return '查看者'
  return '已登录用户'
})
const pageTitle = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : '工作区'))
const breadcrumbs = computed(() => {
  const current = pageTitle.value
  if (route.path.startsWith('/platform/organizations/') && current !== '平台组织') {
    return ['平台组织', current]
  }
  if (route.path.startsWith('/platform/')) return ['平台管理', current]
  if (route.path.startsWith('/organizations/')) return ['组织管理', current]
  return [current]
})

function navigate(path: string): void {
  void router.push(path)
}

async function signOut(): Promise<void> {
  if (signingOut.value) return
  signingOut.value = true
  try {
    await logout()
    await router.replace('/login')
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <div
    v-if="session"
    class="app-shell"
  >
    <aside class="app-sidebar">
      <button
        class="product-identity"
        type="button"
        aria-label="合同智审工作区"
        @click="navigate('/')"
      >
        <span class="product-mark">合</span>
        <span>合同智审</span>
      </button>

      <div class="workspace-context">
        <strong>{{ contextTitle }}</strong>
        <span>{{ contextRole }}</span>
      </div>

      <nav
        class="sidebar-nav"
        aria-label="主导航"
      >
        <template v-if="isPlatformAdmin">
          <p class="nav-group-label">
            平台管理
          </p>
          <ElMenu
            :default-active="route.path.startsWith('/platform/organizations') ? '/platform/organizations' : route.path"
            class="sidebar-menu"
            @select="navigate"
          >
            <ElMenuItem index="/platform/organizations">
              <ElIcon><OfficeBuilding /></ElIcon>
              <span>组织</span>
            </ElMenuItem>
            <ElMenuItem index="/platform/model-configuration">
              <ElIcon><Operation /></ElIcon>
              <span>模型配置</span>
            </ElMenuItem>
          </ElMenu>
        </template>

        <template v-if="currentMembership">
          <p class="nav-group-label">
            组织管理
          </p>
          <ElMenu
            :default-active="route.path"
            class="sidebar-menu"
            @select="navigate"
          >
            <ElMenuItem
              v-if="currentMembership.role === 'org_admin'"
              :index="`/organizations/${currentMembership.organization_id}/settings`"
            >
              <ElIcon><Setting /></ElIcon>
              <span>组织设置</span>
            </ElMenuItem>
            <ElMenuItem
              v-if="currentMembership.role === 'org_admin'"
              :index="`/organizations/${currentMembership.organization_id}/members`"
            >
              <ElIcon><User /></ElIcon>
              <span>成员管理</span>
            </ElMenuItem>
            <ElMenuItem
              v-if="currentMembership.role === 'org_admin'"
              :index="`/organizations/${currentMembership.organization_id}/support-access-grants`"
            >
              <ElIcon><Key /></ElIcon>
              <span>支持授权</span>
            </ElMenuItem>
            <ElMenuItem
              index="/"
            >
              <ElIcon><FolderOpened /></ElIcon>
              <span>当前工作区</span>
            </ElMenuItem>
          </ElMenu>
        </template>
      </nav>
    </aside>

    <div class="app-main">
      <header class="app-header">
        <ElBreadcrumb separator="/">
          <ElBreadcrumbItem
            v-for="breadcrumb in breadcrumbs"
            :key="breadcrumb"
          >
            {{ breadcrumb }}
          </ElBreadcrumbItem>
        </ElBreadcrumb>
        <ElDropdown trigger="click">
          <button
            class="user-menu-trigger"
            type="button"
            aria-label="账户菜单"
          >
            <ElAvatar :size="28">
              <ElIcon><UserFilled /></ElIcon>
            </ElAvatar>
            <span>{{ session.user.display_name }}</span>
            <ElIcon><ArrowDown /></ElIcon>
          </button>
          <template #dropdown>
            <ElDropdownMenu>
              <ElDropdownItem disabled>
                {{ session.user.email }}
              </ElDropdownItem>
              <ElDropdownItem
                divided
                :disabled="signingOut"
                @click="signOut"
              >
                <ElIcon><SwitchButton /></ElIcon>
                退出登录
              </ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>
      </header>

      <main class="app-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
