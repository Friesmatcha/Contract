import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import LoginPage from '@/pages/auth/LoginPage.vue'
import InvitationAcceptPage from '@/pages/auth/InvitationAcceptPage.vue'
import PasswordResetConfirmPage from '@/pages/auth/PasswordResetConfirmPage.vue'
import PasswordResetRequestPage from '@/pages/auth/PasswordResetRequestPage.vue'
import SessionPage from '@/pages/SessionPage.vue'
import { loadSession, sessionState } from '@/features/auth/session'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'session',
    component: SessionPage,
    meta: { requiresAuth: true },
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
  return sessionState.current ? true : { name: 'login', query: { redirect: to.fullPath } }
})

export default router
