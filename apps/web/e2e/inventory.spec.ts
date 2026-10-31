// Ombor (M10, B4.7): jadval va holat guruhlari, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { open } from "./support/page";

test("ombor: jadval, holat guruhi URL'da", async ({ page }) => {
  await mockApi(page);
  await open(page, "/inventory");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ombor");
  const table = page.getByRole("table", { name: "Qoldiq jadvali" });
  await expect(table).toContainText("Kritik");
  await expect(table).toContainText("Xitoyda: 20");
  await page.getByRole("tab", { name: /Kritik/ }).click();
  await expect(page).toHaveURL(/status=critical/);
});

test("gorizontal skroll yo'q (360 px) /inventory", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/inventory");
  await page.getByRole("heading", { level: 1 }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
