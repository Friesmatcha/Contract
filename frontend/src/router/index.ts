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
import ContractFilesPage from '@/pages/contracts/ContractFilesPage.vue'
import ReviewCreatePage from '@/pages/reviews/ReviewCreatePage.vue'
import ReviewProgressPage from '@/pages/reviews/ReviewProgressPage.vue'
import DocumentPreviewPage from '@/pages/documents/DocumentPreviewPage.vue'
import RiskRuleBundleListPage from '@/pages/risks/RiskRuleBundleListPage.vue'
import RiskRuleBundleDetailPage from '@/pages/risks/RiskRuleBundleDetailPage.vue'
import RiskRuleVersionEditorPage from '@/pages/risks/RiskRuleVersionEditorPage.vue'
import ClauseTemplateListPage from '@/pages/clauses/ClauseTemplateListPage.vue'
import ClauseTemplateDetailPage from '@/pages/clauses/ClauseTemplateDetailPage.vue'
import ClauseTemplateVersionEditorPage from '@/pages/clauses/ClauseTemplateVersionEditorPage.vue'
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
        path: 'contracts/:contractId/files',
        name: 'contract-files',
        component: ContractFilesPage,
        meta: { title: '文件版本' },
      },
      {
        path: 'contracts/:contractId/reviews/new',
        name: 'review-create',
        component: ReviewCreatePage,
        meta: { title: '创建审核' },
      },
      {
        path: 'reviews/:reviewTaskId',
        name: 'review-progress',
        component: ReviewProgressPage,
        meta: { title: '审核进度' },
      },
      {
        path: 'documents/:documentVersionId',
        name: 'document-preview',
        component: DocumentPreviewPage,
        meta: { title: '文档预览' },
      },
      {
        path: 'risk-rule-bundles',
        name: 'risk-rule-bundles',
        component: RiskRuleBundleListPage,
        meta: { title: '风险规则' },
      },
      {
        path: 'risk-rule-bundles/:bundleId',
        name: 'risk-rule-bundle-detail',
        component: RiskRuleBundleDetailPage,
        meta: { title: '规则集详情' },
      },
      {
        path: 'risk-rule-bundle-versions/:versionId',
        name: 'risk-rule-version-editor',
        component: RiskRuleVersionEditorPage,
        meta: { title: '规则版本' },
      },
      {
        path: 'clause-templates',
        name: 'clause-templates',
        component: ClauseTemplateListPage,
        meta: { title: '条款模板' },
      },
      {
        path: 'clause-templates/:templateId',
        name: 'clause-template-detail',
        component: ClauseTemplateDetailPage,
        meta: { title: '模板详情' },
      },
      {
        path: 'clause-templates/:templateId/versions/:versionId',
        name: 'clause-template-version-editor',
        component: ClauseTemplateVersionEditorPage,
        meta: { title: '条款版本' },
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
