// Bosh sahifa (M4, ADR-037): uch raqam (naqd + kutilayotgan = jami), formula, Foyda sahifasiga o'tish, mobil, gorizontal
// skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { isMobile, open } from "./support/page";

test("uch raqam: naqd + kutilayotgan = jami sof foyda; formula; 'Qanday hisoblandi' Foyda sahifasiga", async ({ page }) => {
  await mockApi(page);
  await open(page, "/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sof foyda, 1–26-oktabr/);
  await expect(page.getByTestId("net-done")).toHaveText(/31\s508\s700\ssoʻm/);
  await expect(page.getByTestId("net-expected")).toHaveText(/16\s884\s300\ssoʻm/);
  await expect(page.getByTestId("net-profit")).toHaveText(/48\s393\s000\ssoʻm/);
  await page.getByRole("button", { name: "Qanday hisoblanadi: Kutilayotgan sof foyda" }).click();
  await expect(page.getByText(/xuddi naqd kabi/)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Qanday hisoblandi — «Foyda» sahifasida" }).click();
  await expect(page).toHaveURL(/\/pnl/);
  await expect(page.getByRole("table", { name: "Foyda va zarar: tushumdan sof foydagacha" })).toBeVisible();
});

test("mobil: uch raqam ustma-ust, grafikda 'Tushum'ga o'tish; SKU tablari", async ({ page }, info) => {
  test.skip(!isMobile(info.project.name), "faqat mobil");
  await mockApi(page);
  await open(page, "/");
  const done = await page.getByTestId("net-done").boundingBox();
  const total = await page.getByTestId("net-profit").boundingBox();
  expect(total!.y).toBeGreaterThan(done!.y); // ustma-ust (bir qatorda emas)
  await page.getByRole("radio", { name: "Tushum" }).check();
  await expect(page.getByRole("img", { name: /Kunlik tushum: yakunlangan va jarayonda/ })).toBeVisible();
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
