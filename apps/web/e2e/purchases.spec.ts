// Xaridlar (M9, B4.6): ro'yxatdan xarid sahifasiga, Partiya yo'li va tannarx tarkibi, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { PURCHASE_1 } from "../src/test/purchases";
import { mockApi } from "./support/api";
import { open } from "./support/page";

test("ro'yxat → xarid sahifasi: Partiya yo'li, qatorlar, tannarx tarkibi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/purchases");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Xaridlar");
  await page.getByRole("link", { name: "Oktabr partiyasi" }).click();
  await expect(page).toHaveURL(new RegExp(`/purchases/${PURCHASE_1}$`));
  await expect(page.getByRole("list", { name: "Partiya yoʻli" }).getByRole("listitem")).toHaveCount(8);
  await expect(page.getByRole("table", { name: "Qatorlar" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: /Birlik tannarx tarkibi/ })).toContainText("kargo kiritilmagan");
});

for (const path of ["/purchases", `/purchases/${PURCHASE_1}`]) {
  test(`gorizontal skroll yo'q (360 px) ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await mockApi(page);
    await open(page, path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
