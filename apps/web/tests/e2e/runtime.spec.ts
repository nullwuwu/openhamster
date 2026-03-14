import { expect, test } from '@playwright/test'

test('runtime page shows pipeline detail and logs', async ({ page }) => {
  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/command') && response.status() === 200)
  await page.goto('/runtime')
  await responsePromise

  await expect(page.getByRole('heading', { name: /Runtime Detail|运行详情/ })).toBeVisible()
  await expect(page.getByText(/Pipeline Detail|Pipeline 详情/)).toBeVisible()
  await expect(page.getByText(/Runtime Logs|运行日志/)).toBeVisible()
  await expect(page.getByText(/Dependencies|运行依赖/)).toBeVisible()
})
