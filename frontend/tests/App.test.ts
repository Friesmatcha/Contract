import { render, screen } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, test } from 'vitest'

import App from '@/App.vue'
import { routes } from '@/router'

test('renders the login route', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  router.push('/login')
  await router.isReady()

  render(App, { global: { plugins: [router, ElementPlus] } })

  expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
})
