import { expect, test } from "@playwright/test";

test("research detail page shows backtest admission and causal chain", async ({
  page,
}) => {
  const proposalsResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/research/proposals") &&
      response.status() === 200,
  );
  await page.goto("/research");
  const response = await proposalsResponse;
  const proposals = await response.json();
  expect(Array.isArray(proposals)).toBeTruthy();
  expect(proposals.length).toBeGreaterThan(0);

  const proposalId = proposals[0].id;
  await page.goto(`/research/${proposalId}`);

  await expect(
    page.getByRole("heading", { name: /Research Detail|研究详情/ }),
  ).toBeVisible();
  await expect(
    page.getByText(/Backtest Admission|回测准入/).first(),
  ).toBeVisible();
  await expect(page.getByText(/Research Causal View|研究因果链/)).toBeVisible();
  await expect(page.getByText(/Backtest Terms|回测术语说明/)).toBeVisible();
});
