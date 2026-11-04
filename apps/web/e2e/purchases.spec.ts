// Xaridlar (M9, B4.6): ro'yxatdan xarid sahifasiga, Partiya yo'li va tannarx tarkibi, gorizontal skrollsiz (360 px).
import { expect, test } from "@playwright/test";

import { PURCHASE_1 } from "../src/test/purchases";
import { SHIPMENT_1 } from "../src/test/shipments";
import { mockApi } from "./support/api";
import { open } from "./support/page";

test("ro'yxat → xarid sahifasi: Partiya yo'li, tovarlar, tannarx tarkibi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/purchases");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Xaridlar");
  await page.getByRole("link", { name: "Oktabr partiyasi" }).click();
  await expect(page).toHaveURL(new RegExp(`/purchases/${PURCHASE_1}$`));
  await expect(page.getByRole("list", { name: "Partiya yoʻli" }).getByRole("listitem")).toHaveCount(8);
  await expect(page.getByRole("table", { name: "Partiyadagi tovarlar" })).toBeVisible();
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

test("tovar qo'shish oynasi: bir nechta SKU tanlash, 360 px da gorizontal skrollsiz", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, `/purchases/${PURCHASE_1}`);
  await page.getByRole("button", { name: "Tovar qoʻshish" }).click();
  const dialog = page.getByRole("dialog", { name: "Tovar qoʻshish" });
  await dialog.getByRole("combobox", { name: "Tovar" }).click();
  const list = dialog.getByRole("listbox");
  await expect(list.getByRole("option")).toHaveCount(3); // arxivlangan va bloklangan ham
  await list.getByRole("option", { name: /ARCHIVED/ }).click();
  await dialog.getByRole("combobox", { name: "Yana SKU qoʻshish" }).click();
  await dialog.getByRole("listbox").getByRole("option", { name: /BLOCKED/ }).click();
  await expect(dialog.getByRole("list", { name: "Tanlangan SKUʼlar" }).getByRole("listitem")).toHaveCount(2);
  const overflow = await dialog.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("kargolar: ro'yxatdan kargo sahifasiga, xaridlar va kargo ulushi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/purchases");
  await page.getByRole("link", { name: "Kargolar" }).click();
  await expect(page).toHaveURL(/\/shipments$/);
  await page.getByRole("link", { name: "Presslangan oʻram" }).click();
  await expect(page).toHaveURL(new RegExp(`/shipments/${SHIPMENT_1}$`));
  await expect(page.getByRole("table", { name: "Kargodagi xaridlar" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Tovarlar va kargo ulushi" })).toBeVisible();
});

for (const path of ["/shipments", `/shipments/${SHIPMENT_1}`]) {
  test(`gorizontal skroll yo'q (360 px) ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await mockApi(page);
    await open(page, path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
