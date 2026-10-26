// Bosh sahifa (M4, B4.1): hisob varag'i, drill-down, mobilda yig'ilgan ko'rinish, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { isMobile, open } from "./support/page";

test("hisob varag'i: sof foyda, qatorlar, o'zgarish; formula", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sof foyda, 1–26-oktabr/);
  await expect(page.getByTestId("net-profit")).toHaveText(/48\s393\s000\ssoʻm/);
  const ledger = page.getByRole("table", { name: "Hisob varagʻi: tushumdan sof foydagacha" });
  await expect(ledger.getByRole("row", { name: /^Sof foyda/ })).toBeVisible();
  if (isMobile(info.project.name)) await page.getByRole("button", { name: "Barcha qatorlar" }).click(); // Soliq mobilda yig'ilgan
  await page.getByRole("button", { name: "Qanday hisoblanadi: Soliq" }).click();
  await expect(page.getByText("Soliq profili boʻyicha")).toBeVisible();
});

test("qatorni bosish — manba yozuvlar drawer'da; Esc yopadi", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  if (isMobile(info.project.name)) await page.getByRole("button", { name: "Barcha qatorlar" }).click();
  await page.getByRole("table", { name: /Hisob varagʻi/ }).getByRole("button", { name: "Uzum komissiyasi", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "Uzum komissiyasi" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("Sumka qora M")).toBeVisible();
  await expect(drawer.getByRole("table")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("mobil: ledger yig'ilgan (3 qator) va 'Barcha qatorlar' ochadi; SKU tablari", async ({ page }, info) => {
  test.skip(!isMobile(info.project.name), "faqat mobil");
  await mockApi(page);
  await open(page, "/");
  const ledger = page.getByRole("table", { name: /Hisob varagʻi/ });
  await expect(ledger.getByRole("row")).toHaveCount(3); // yashirin qatorlar `display: none` — hisobga olinmaydi
  await page.getByRole("button", { name: "Barcha qatorlar" }).click();
  await expect(ledger.getByRole("row")).toHaveCount(10);
  await page.getByRole("tab", { name: "Zarar qilayotgan 5" }).click();
  await expect(page.getByRole("table", { name: "Zarar qilayotgan 5" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Eng foydali 5" })).toBeHidden();
});

test("gorizontal skroll yo'q (360 px)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
