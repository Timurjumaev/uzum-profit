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
  await expect(page.getByRole("list", { name: "Partiya yoʻli" }).getByRole("listitem")).toHaveCount(3); // ADR-061: Yoʻlda → Omborimda → Uzumda
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

test("yangi xarid oynasi (ADR-061 §2): tovar, jami toʻlandi, kurs, trek — 360 px da gorizontal skrollsiz", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/purchases");
  await page.getByRole("button", { name: "Yangi xarid" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Yangi xarid (partiya)" });
  await dialog.getByRole("combobox", { name: "Tovarlar" }).click();
  await dialog.getByRole("listbox").getByRole("option").first().click();
  await dialog.getByLabel(/^Yangi tovar/).fill("Paket");
  await dialog.getByRole("button", { name: "Qoʻshish" }).click();
  await expect(dialog.getByRole("list", { name: "Tanlangan SKUʼlar" }).getByRole("listitem")).toHaveCount(2);
  await expect(dialog.getByLabel(/^Qator summasi/)).toHaveCount(2);
  await expect(dialog.getByLabel(/^Jami toʻlandi/)).toBeVisible();
  await expect(dialog.getByLabel(/^Trek raqami/)).toBeVisible();
  const overflow = await dialog.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("sanash oynasi (TM4): − / + 44 px, brak, 360 px da gorizontal skrollsiz", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, `/purchases/${PURCHASE_1}`);
  await page.getByRole("button", { name: "Sanash" }).click();
  const dialog = page.getByRole("dialog", { name: "Sanash" });
  await dialog.getByRole("button", { name: "Hammasi keldi" }).click();
  await expect(dialog.getByLabel("Kelgan: Mashina")).toHaveValue("100");
  await dialog.getByRole("button", { name: "Bittaga kamaytirish: Mashina" }).click();
  await expect(dialog.getByLabel("Kelgan: Mashina")).toHaveValue("99");
  const box = await dialog.getByRole("button", { name: "Bittaga koʻpaytirish: Mashina" }).boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(43.5);
  expect(box!.height).toBeGreaterThanOrEqual(43.5);
  await expect(dialog.getByLabel(/^Sotuvchi qaytargan summa/)).toBeVisible();
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

test("kargo puli (TM3): kartochkalar, kodli quti paneli — 360 px da gorizontal skrollsiz", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/purchases");
  await page.getByRole("link", { name: "Kargo puli" }).click();
  await expect(page).toHaveURL(/\/cargo-pool$/);
  const list = page.getByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
  await expect(list.getByRole("listitem")).toHaveCount(3);
  await page.getByLabel("Kargo puli: Oktabr partiyasi").fill("45");
  await expect(page.getByRole("button", { name: "Kargo pulini saqlash (1)" })).toBeEnabled();
  await page.getByRole("checkbox", { name: "Qutiga qoʻshish: Kabel va gʻiloflar" }).check();
  await page.getByRole("checkbox", { name: "Qutiga qoʻshish: Kichik buyurtma" }).check();
  const panel = page.getByRole("region", { name: "Bitta qutiga birlashtirish" });
  await panel.getByLabel(/^Umumiy summa/).fill("100");
  await expect(page.getByLabel("Qutidagi ulush: Kichik buyurtma")).toHaveValue("50,00");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

for (const path of ["/shipments", `/shipments/${SHIPMENT_1}`, "/cargo-pool"]) {
  test(`gorizontal skroll yo'q (360 px) ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await mockApi(page);
    await open(page, path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
