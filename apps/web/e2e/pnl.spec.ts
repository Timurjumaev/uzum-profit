// Foyda va zarar (M5, B4.2): hisob varag'i ustunlari, drill-down, kesimlar URL'da, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { isMobile, open } from "./support/page";

test("hisob varag'i: yalpi foyda, ustunlar; drill-down", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/pnl");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Foyda va zarar, /);
  const ledger = page.getByRole("table", { name: "Foyda va zarar: tushumdan sof foydagacha" });
  await expect(ledger.getByRole("row", { name: /^Yalpi foyda/ })).toBeVisible();
  await expect(page.getByText(/Standart tarif/)).toHaveCount(0); // o'ylab topilgan qator yo'q
  // ADR-035: Uzum bonusi haqida savol va banner yo'q — API nima bersa, shu.
  await expect(page.getByText("Uzum logistikani olmagan koʻrinadi")).toHaveCount(0);
  // Tor ekranda faqat joriy summa — qo'shimcha ustunlar yashirin.
  const previous = ledger.getByRole("columnheader", { name: "Oldingi davr" });
  if (isMobile(info.project.name)) await expect(previous).toBeHidden();
  else await expect(previous).toBeVisible();
  await expect(page.getByText(/tannarxsiz — foydaga kirmadi/)).toBeVisible();
  await ledger.getByRole("button", { name: "Tushum", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "Tushum" });
  await expect(drawer.getByText("Sumka qora M")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("kesimlar: Do'konlar / SKU — URL'da, havola bilan ochiladi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/pnl");
  await expect(page.getByRole("table", { name: "Oylar" })).toBeVisible();
  await page.getByRole("tab", { name: "SKU" }).click();
  await expect(page).toHaveURL(/view=sku/);
  const skus = page.getByRole("table", { name: "SKU" });
  await expect(skus.getByRole("rowheader").first()).toHaveText("Sumka qora M");
  await page.reload();
  await expect(page.getByRole("tab", { name: "SKU" })).toHaveAttribute("aria-selected", "true");
});

for (const view of ["", "?view=sku"]) {
  test(`gorizontal skroll yo'q (360 px) ${view || "oylar"}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await mockApi(page);
    await open(page, `/pnl${view}`);
    await page.getByRole("table", { name: view ? "SKU" : "Oylar" }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
