import { render, screen } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, test } from 'vitest'

import App from '@/App.vue'
import { routes } from '@/router'

test('renders the bootstrap route', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  router.push('/')
  await router.isReady()

  render(App, { global: { plugins: [router] } })

  expect(screen.getByRole('heading', { name: '合同审核系统' })).toBeInTheDocument()
  expect(screen.getByText('工程基线已就绪')).toBeInTheDocument()
})
