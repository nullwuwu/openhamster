import { expect, test } from '@playwright/test'

test('paper page shows latest execution evidence', async ({ page }) => {
  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/v1/paper/active-strategy') && response.status() === 200)
  await page.goto('/paper')
  const response = await responsePromise
  const payload = await response.json()

  expect(payload.paper_trading.latest_execution).toBeTruthy()

  await expect(page.getByRole('heading', { name: /Paper Execution Console|模拟盘执行面板/ })).toBeVisible()
  await expect(page.getByText(/Latest Execution|最近一次执行/)).toBeVisible()
  await expect(page.getByText(/Execution Explanation|执行解释/)).toBeVisible()
  await expect(page.getByText(/Signal|信号/).first()).toBeVisible()
  await expect(page.getByText(/Price As Of|价格时间/)).toBeVisible()
})
