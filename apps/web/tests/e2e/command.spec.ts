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

  if (payload.llm_status.using_mock_fallback || payload.market_snapshot.macro_status.degraded) {
    await expect(page.getByText(/当前仍是样例模式|Sample mode is still active/).first()).toBeVisible()
  } else {
    await expect(page.getByText('当前仍是样例模式')).toHaveCount(0)
    await expect(page.getByText('Sample mode is still active')).toHaveCount(0)
  }
  await expect(page.getByRole('heading', { name: /The system is not yet ready for live trading|系统当前还不具备实盘条件/ })).toBeVisible()
  await expect(page.getByText(/Three Key Reasons|三个最关键原因/)).toBeVisible()
  await expect(page.getByText(/Not Ready For Live|尚未具备实盘条件/).first()).toBeVisible()
})
