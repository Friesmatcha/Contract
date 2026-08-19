import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import LoginPage from '@/pages/auth/LoginPage.vue'
import InvitationAcceptPage from '@/pages/auth/InvitationAcceptPage.vue'
import PasswordResetConfirmPage from '@/pages/auth/PasswordResetConfirmPage.vue'
import PasswordResetRequestPage from '@/pages/auth/PasswordResetRequestPage.vue'
import SessionPage from '@/pages/SessionPage.vue'
import AppShell from '@/components/AppShell.vue'
import OrganizationSettingsPage from '@/pages/organization/OrganizationSettingsPage.vue'
import OrganizationMembersPage from '@/pages/organization/OrganizationMembersPage.vue'
import SupportAccessPage from '@/pages/organization/SupportAccessPage.vue'
import PlatformModelConfigurationPage from '@/pages/platform/PlatformModelConfigurationPage.vue'
import PlatformOrganizationDetailPage from '@/pages/platform/PlatformOrganizationDetailPage.vue'
import PlatformOrganizationsPage from '@/pages/platform/PlatformOrganizationsPage.vue'
import ContractListPage from '@/pages/contracts/ContractListPage.vue'
import CreateContractPage from '@/pages/contracts/CreateContractPage.vue'
import ContractDetailPage from '@/pages/contracts/ContractDetailPage.vue'
import { defaultLandingPath, loadSession, sessionState } from '@/features/auth/session'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    meta: { requiresAuth: true },
    component: AppShell,
    children: [
      {
        path: '',
        name: 'session',
        component: SessionPage,
        meta: { title: '当前工作区' },
      },
      {
        path: 'platform/organizations',
        name: 'platform-organizations',
        component: PlatformOrganizationsPage,
        meta: { title: '平台组织' },
      },
      {
        path: 'platform/organizations/:organizationId',
        name: 'platform-organization-detail',
        component: PlatformOrganizationDetailPage,
        meta: { title: '组织详情' },
      },
      {
        path: 'platform/model-configuration',
        name: 'platform-model-configuration',
        component: PlatformModelConfigurationPage,
        meta: { title: '模型配置' },
      },
      {
        path: 'contracts',
        name: 'contracts',
        component: ContractListPage,
        meta: { title: '合同目录' },
      },
      {
        path: 'contracts/new',
        name: 'contract-create',
        component: CreateContractPage,
        meta: { title: '创建合同' },
      },
      {
        path: 'contracts/:contractId',
        name: 'contract-detail',
        component: ContractDetailPage,
        meta: { title: '合同详情' },
      },
      {
        path: 'organizations/:organizationId/settings',
        name: 'organization-settings',
        component: OrganizationSettingsPage,
        meta: { title: '组织设置' },
      },
      {
        path: 'organizations/:organizationId/members',
        name: 'organization-members',
        component: OrganizationMembersPage,
        meta: { title: '成员管理' },
      },
      {
        path: 'organizations/:organizationId/support-access-grants',
        name: 'support-access-grants',
        component: SupportAccessPage,
        meta: { title: '支持授权' },
      },
    ],
  },
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
  },
  {
    path: '/password-reset',
    name: 'password-reset-request',
    component: PasswordResetRequestPage,
  },
  {
    path: '/password-reset/confirm',
    name: 'password-reset-confirm',
    component: PasswordResetConfirmPage,
  },
  {
    path: '/invitations/accept',
    name: 'invitation-accept',
    component: InvitationAcceptPage,
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth) return true
  if (!sessionState.loaded) await loadSession()
  if (!sessionState.current) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'session') {
    const landing = defaultLandingPath(sessionState.current)
    if (landing !== '/') return landing
  }
  return true
})

export default router
