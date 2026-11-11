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

test("soliq profili formasi: shablon qatorlari 360 px da sig'adi (gorizontal skroll yo'q)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/settings");
  await page.getByRole("button", { name: "Profil qoʻshish" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Yangi soliq profili" });
  await dialog.getByLabel("Tayyor shablon").selectOption("yatt");
  await expect(dialog.getByRole("group", { name: "Soliq qatori 2" })).toBeVisible();
  const overflow = await page.evaluate(() => {
    const d = document.querySelector("[role=dialog]") as HTMLElement;
    return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, dialog: d.scrollWidth - d.clientWidth };
  });
  expect(overflow.page).toBeLessThanOrEqual(0);
  expect(overflow.dialog).toBeLessThanOrEqual(0);
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT });
});
