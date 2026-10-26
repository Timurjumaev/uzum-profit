// Karkas (04 §7.1): menyu (desktop sidebar / mobil tab bar), Ctrl+K, filtrlar URL'da, mavzu, chiqish, holat sahifasi.
import { expect, test } from "@playwright/test";

import { mockApi } from "./support/api";
import { isMobile, open } from "./support/page";

test("menyu: sahifaga o'tish, faol bo'lim belgilanadi", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  const menu = page.getByRole("navigation", { name: isMobile(info.project.name) ? "Pastki menyu" : "Asosiy menyu" });
  await expect(menu).toBeVisible();
  await expect(page.getByRole("navigation", { name: isMobile(info.project.name) ? "Asosiy menyu" : "Pastki menyu" })).toBeHidden();
  await menu.getByRole("link", { name: "Foyda" }).click();
  await expect(page).toHaveURL(/\/pnl$/);
  await expect(page.getByRole("heading", { level: 1, name: /^Foyda va zarar/ })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Foyda" })).toHaveAttribute("aria-current", "page");
});

test("Ctrl+K / qidiruv tugmasi: sahifaga tez o'tish (lotin va kirill)", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  if (isMobile(info.project.name)) await page.getByRole("button", { name: "Tez oʻtish" }).click();
  else await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Tez oʻtish" });
  await expect(palette).toBeVisible();
  await palette.getByRole("combobox").fill("омбор"); // kirillda "Ombor"
  await expect(palette.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/inventory$/);
  await expect(palette).toBeHidden();
});

test("davr va solishtirish URL'da; bo'limga o'tganda saqlanadi", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  await page.getByRole("button", { name: /^Davr:/ }).click();
  await page.getByRole("button", { name: "7 kun" }).click();
  await expect(page).toHaveURL(/from=2026-10-20&to=2026-10-26/);
  if (!isMobile(info.project.name)) {
    // Solishtirish topbar'da (mobilda — "Yana" panelida).
    await page.getByRole("button", { name: "Solishtirish" }).click();
    await page.getByRole("radio", { name: "Oldingi davr" }).click({ force: true }); // tanlansa panel yopiladi
    await expect(page).toHaveURL(/cmp=previous/);
  }
  const menu = page.getByRole("navigation", { name: isMobile(info.project.name) ? "Pastki menyu" : "Asosiy menyu" });
  await menu.getByRole("link", { name: "Ombor" }).click();
  await expect(page).toHaveURL(/\/inventory\?.*from=2026-10-20&to=2026-10-26/);
  if (!isMobile(info.project.name)) await expect(page).toHaveURL(/cmp=previous/);
  await expect(page.getByRole("button", { name: /^Davr: 7 kun/ })).toBeVisible();
});

test("mavzu: tanlov saqlanadi (qayta yuklasa ham)", async ({ page }, info) => {
  await mockApi(page);
  await open(page, "/");
  if (isMobile(info.project.name)) await page.getByRole("button", { name: "Tez oʻtish" }).click();
  else await page.keyboard.press("Control+k");
  await page.getByRole("combobox").fill("qorongi");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("chiqish: sessiya tugaydi, /login ga", async ({ page }, info) => {
  const api = await mockApi(page);
  await open(page, "/");
  if (isMobile(info.project.name)) {
    await page.getByRole("navigation", { name: "Pastki menyu" }).getByRole("button", { name: "Yana" }).click();
    await page.getByRole("dialog", { name: "Yana" }).getByRole("button", { name: "Chiqish" }).click();
  } else {
    await page.getByRole("button", { name: /^Hisob:/ }).click();
    await page.getByRole("button", { name: "Chiqish" }).click();
  }
  await expect(page).toHaveURL(/\/login$/);
  expect(api.bodies("POST", "/auth/logout")).toEqual([null]);
});

test("Maʼlumotlar holati: do'kon jadvallari va akkaunt", async ({ page }) => {
  await mockApi(page);
  await open(page, "/status");
  await expect(page.getByRole("heading", { level: 1, name: "Maʼlumotlar holati" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Durii: Maʼlumotlar holati" })).toBeVisible();
  await expect(page.getByRole("table", { name: "EL-ONE: Maʼlumotlar holati" })).toBeVisible();
  await expect(page.getByText("Ishlayapti")).toBeVisible();
  await page.getByRole("button", { name: "Hozir yangilash" }).click();
  await expect(page.getByText("Yangilash boshlandi")).toBeVisible();
});
