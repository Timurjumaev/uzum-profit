// Buyurtmalar (M7): ro'yxat, bekor va qaytarish tahlili — 360 px da sahifa gorizontal skroll qilmaydi (tamoyil 10).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { open } from "./support/page";

for (const [name, path, heading] of [
  ["ro'yxat", "/orders", null],
  ["bekor bo'lish", "/orders?tab=cancel", "Bekor sabablari"],
  ["qaytarilish", "/orders?tab=returns", "Qaytarish sabablari"],
] as const) {
  test(`gorizontal skroll yo'q (360 px) — Buyurtmalar: ${name}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await mockApi(page);
    await open(page, path);
    await page.getByRole("heading", { level: 1, name: /^Buyurtmalar/ }).waitFor();
    if (heading) await page.getByRole("heading", { name: heading }).waitFor(); // tahlil jadvallari chizildi
    else await page.getByRole("table").first().waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("ro'yxat ko'rinishi (360 px, ADR-057 Q11): sana (ostida holat), SKU, yalpi foyda; jadval ichida skroll yo'q", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/orders");
  const table = page.locator(".orders-list table");
  await table.waitFor();
  const visible = await table.locator("thead th").evaluateAll((ths) => ths.filter((th) => getComputedStyle(th).display !== "none").length);
  expect(visible).toBe(3);
  await expect(table.locator(".orders-cell__mobile-meta").first()).toBeVisible();
  const inner = await page.locator(".orders-list .ui-table-wrap").evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(inner).toBeLessThanOrEqual(1);
});
