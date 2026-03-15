import { expect, test } from "@playwright/test";

test("paper detail page shows orders, positions, and governance context", async ({
  page,
}) => {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/paper/active-strategy") &&
      response.status() === 200,
  );
  await page.goto("/paper/detail");
  await responsePromise;

  await expect(
    page.getByRole("heading", { name: /Paper Detail|模拟盘详情/ }),
  ).toBeVisible();
  await expect(page.getByText(/Latest Orders|最近订单/)).toBeVisible();
  await expect(page.getByText(/Recovery Context|恢复上下文/)).toBeVisible();
  await expect(page.getByText(/Latest Execution|最近一次执行/)).toBeVisible();
});
