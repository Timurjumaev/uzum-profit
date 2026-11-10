// Mahsulotlar (M6, B4.48): sahifalash — sahifa raqamlari, o'lcham tanlovi, URL'da `page`, 360 px'da gorizontal skrollsiz.
import { expect, test } from "@playwright/test";

import { skuDetail, skuRow } from "../src/test/products";
import { mockApi } from "./support/api";
import { open } from "./support/page";

const TABLE = "Mahsulotlar: SKU boʻyicha sotuv va foyda";

test("mahsulotlar: sahifalash — keyingi sahifa URL'da, o'lcham o'zgarsa 1-sahifa", async ({ page }) => {
  await mockApi(page);
  await open(page, "/products");
  const table = page.getByRole("table", { name: TABLE });
  await expect(table.getByRole("rowheader")).toHaveCount(50);
  await expect(table.getByRole("rowheader").first()).toContainText("Tovar 001");
  await expect(page.getByText(/1–50 \/ 120 ta/)).toBeVisible();

  await page.getByRole("button", { name: "Keyingi sahifa" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(table.getByRole("rowheader").first()).toContainText("Tovar 051");
  await expect(page.getByText(/51–100 \/ 120 ta/)).toBeVisible();

  await page.getByRole("button", { name: "3-sahifa" }).click();
  await expect(table.getByRole("rowheader")).toHaveCount(20);
  await expect(page.getByRole("button", { name: "Keyingi sahifa" })).toBeDisabled();

  await page.getByLabel("Sahifada").selectOption("20");
  await expect(page).not.toHaveURL(/page=/);
  await expect(table.getByRole("rowheader")).toHaveCount(20);
  await expect(page.getByText(/1–20 \/ 120 ta/)).toBeVisible();

  // O'lcham brauzerda eslanadi: sahifani qayta ochganda ham 20 tadan.
  await page.reload();
  await expect(page.getByRole("table", { name: TABLE }).getByRole("rowheader")).toHaveCount(20);
});

test("gorizontal skroll yo'q (360 px) /products", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockApi(page);
  await open(page, "/products?page=3");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await expect(page.getByRole("navigation", { name: "Sahifalar" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

const SKU = "51111111-1111-4111-8111-111111111111";

/** Ko'rinadigan tugma, havola va maydonlardan bosish maydoni 44 px dan kichigi (sahifa ichidagilar; yuqori panel — umumiy qobiq). */
async function smallTargets(page: import("@playwright/test").Page, scope: string) {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel)!;
    return [...root.querySelectorAll("a,button,select,input,[role=tab]")]
      .map((e) => ({ name: (e.textContent || e.getAttribute("aria-label") || e.tagName).trim().slice(0, 40), box: e.getBoundingClientRect() }))
      .filter((x) => x.box.width > 0 && x.box.height > 0 && (x.box.height < 43.5 || x.box.width < 43.5))
      .map((x) => `${x.name}: ${Math.round(x.box.width)}×${Math.round(x.box.height)}`);
  }, scope);
}

test.describe("mobil (360 px)", () => {
  test.use({ viewport: { width: 360, height: 800 }, hasTouch: true });

  test("SKU sahifasi: gorizontal skroll yo'q, KPI'lar ikki ustunda, bosish maydoni ≥ 44 px (B4.54)", async ({ page }) => {
    await mockApi(page);
    await open(page, `/products/${SKU}`);
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const kpis = page.locator(".sku__kpis > *");
    const first = await kpis.nth(0).boundingBox();
    const second = await kpis.nth(1).boundingBox();
    expect(Math.abs(first!.y - second!.y)).toBeLessThan(2); // bitta qatorda — ikki ustun
    expect(await smallTargets(page, ".sku")).toEqual([]);
  });

  test("Mahsulotlar jadvali: bosish maydoni ≥ 44 px, jadval o'z ichida skroll qiladi (B4.54)", async ({ page }) => {
    await mockApi(page);
    await open(page, "/products");
    await page.getByRole("table", { name: TABLE }).waitFor();
    expect(await smallTargets(page, ".products")).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test("SKU sahifasi (1000 px): katta KPI raqami kesilmaydi, grafik jadvali o'z ichida skroll qiladi (B4.56)", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 900 });
  await mockApi(page);
  // Katta summalar + uzun kunlik tarix (har kun ma'lumotli) — jadval ko'rinishi uzun bo'ladi.
  const history = Array.from({ length: 26 }, (_, i) => ({
    day: `2026-10-${String(i + 1).padStart(2, "0")}`,
    units: 1,
    revenue: "100000.00",
    net_profit: "20000.00",
    profit_per_unit: "20000.00",
    price: "200000.00",
    commission_pct: null,
    stock: 10,
  }));
  const detail = skuDetail({ sku: skuRow({ revenue: "4353060000.00", net_profit: "1472780000.00", avg_price: "28451000.00" }), history });
  await page.route(`**/api/v1/orgs/*/skus/${SKU}*`, (route) => route.fulfill({ json: detail }));
  await open(page, `/products/${SKU}?from=2026-10-01&to=2026-10-26`);
  await page.getByRole("heading", { level: 1 }).waitFor();
  // Raqam kartadan o'ng chetga chiqib ketmasin (kesilgan "4 353 060 so'" — B4.56).
  const clipped = await page.evaluate(() =>
    [...document.querySelectorAll(".sku__kpis .ui-kpi")]
      .filter((card) => card.querySelector(".kpi")!.getBoundingClientRect().right > card.getBoundingClientRect().right - 8)
      .map((card) => card.textContent),
  );
  expect(clipped).toEqual([]);
  // Kunlik tushum grafigi jadval ko'rinishida: uzun jadval o'z ichida skroll qiladi (karta cheksiz cho'zilmaydi).
  await page.locator(".chart-frame").first().getByLabel("Jadval").check({ force: true });
  const table = await page.locator(".chart-frame").first().boundingBox();
  expect(table!.height).toBeLessThan(600);
});
