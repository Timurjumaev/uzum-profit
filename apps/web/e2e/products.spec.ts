// Mahsulotlar (M6, B4.48): sahifalash — sahifa raqamlari, o'lcham tanlovi, URL'da `page`, 360 px'da gorizontal skrollsiz.
import { expect, test } from "@playwright/test";

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
