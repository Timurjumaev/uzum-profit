// Boshlang'ich holat (B4.12, F41): sahifa ochiladi, qatorlar va qamrov ko'rinadi, 360 px'da gorizontal skroll yo'q.
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { open } from "./support/page";

test("boshlang'ich holat: qatorlar va qamrov", async ({ page }) => {
  await mockApi(page);
  await open(page, "/opening");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Boshlangʻich holat");
  await expect(page.getByText("Soat", { exact: true })).toBeVisible();
  await expect(page.getByText("Sumka", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Boshlash sanasi")).toHaveValue("2026-11-01");
});

test("gorizontal skroll yo'q (360 px) /opening", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/opening");
  await page.getByText("Sumka", { exact: true }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
