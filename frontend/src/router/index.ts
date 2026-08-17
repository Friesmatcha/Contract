import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import BootstrapPage from '@/pages/BootstrapPage.vue'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'bootstrap',
    component: BootstrapPage,
  },
]

const router = createRouter({ history: createWebHistory(), routes })

export default router
