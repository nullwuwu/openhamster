import { expect, test } from '@playwright/test'

test('command page renders executive summary with live runtime semantics', async ({ page }) => {
  const commandResponse = page.waitForResponse((response) => response.url().includes('/api/v1/command') && response.status() === 200)
  await page.goto('/')
  const response = await commandResponse
  const payload = await response.json()

  expect(payload.llm_status.provider).toBe('minimax')
  expect(payload.active_strategy.proposal.source_kind).toBe('minimax')
  expect(typeof payload.market_snapshot.macro_status.status).toBe('string')
  expect(payload.market_snapshot.macro_status.provider).toBeTruthy()

  await expect(page.getByText(/Executive Summary/)).toBeVisible()
  await expect(page.getByText(/Pipeline Stages/)).toBeVisible()
  await expect(page.getByText(/Stage Evidence/)).toBeVisible()
  await expect(page.getByRole('button', { name: /Run Now|立即研究一次/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'MiniMax' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Mock' })).toHaveCount(0)
  await expect(page.getByText(/Open Runtime Detail（打开运行详情）|Open Runtime Detail/)).toBeVisible()
})
