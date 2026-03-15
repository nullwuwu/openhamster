import { expect, test } from "@playwright/test";

test("research detail page shows backtest admission and causal chain", async ({
  page,
}) => {
  await page.goto("/research");
  const detailLink = page.getByRole("link", {
    name: /Open Research Detail|查看研究详情/,
  });
  await expect(detailLink.first()).toBeVisible();
  await detailLink.first().click();

  await expect(
    page.getByRole("heading", { name: /Research Detail|研究详情/ }),
  ).toBeVisible();
  await expect(
    page.getByText(/Backtest Admission|回测准入/).first(),
  ).toBeVisible();
  await expect(page.getByText(/Research Causal View|研究因果链/)).toBeVisible();
  await expect(page.getByText(/Backtest Terms|回测术语说明/)).toBeVisible();
});
