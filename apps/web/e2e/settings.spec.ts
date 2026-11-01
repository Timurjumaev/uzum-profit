// Sozlamalar (M16, B4.8): bo'limlar ko'rinadi, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { open } from "./support/page";

test("sozlamalar: hamma bo'lim ko'rinadi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/settings");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sozlamalar");
  for (const title of ["Tannarx usuli", "Soliq profili", "Uzum toʻlov jadvali", "Muddatlar va qamrov", "Doʻkonlar"]) {
    await expect(page.getByRole("heading", { level: 2, name: title })).toBeVisible();
  }
  await expect(page.getByRole("table", { name: "Soliq profili" })).toContainText("Amalda");
});

test("gorizontal skroll yo'q (360 px) /settings", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/settings");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await page.getByRole("table", { name: "Soliq profili" }).waitFor();
  await page.getByRole("heading", { level: 2, name: "Doʻkonlar" }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
