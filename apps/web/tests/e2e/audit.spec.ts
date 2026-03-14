import { expect, test } from '@playwright/test'

test('audit page shows live readiness history', async ({ page }) => {
  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/audit/events') && response.status() === 200)
  await page.goto('/audit')
  await responsePromise

  await expect(page.getByRole('heading', { name: /Audit and Rollback Ledger|审计与回滚台账/ })).toBeVisible()
  await expect(page.getByText(/Latest Readiness Evaluation|最近一次评估/)).toBeVisible()
  await expect(page.getByText(/Change vs Previous Evaluation|相对上一轮变化/)).toBeVisible()
  await expect(page.getByText(/Show Advanced Audit Sections|展开高级审计内容/)).toBeVisible()
})
