// Kirish (M1): telefon → Telegram kodi → kirish; xato; qaytish manzili; til.
import { expect, test } from "@playwright/test";

import { GOOD_CODE, mockApi, PHONE } from "./support/api";
import { open } from "./support/page";

test("telefon → kod → bosh sahifa; raqam yagona ko'rinishda, kod to'g'ri yuboriladi", async ({ page }) => {
  const api = await mockApi(page, { me: null });
  await open(page, "/login");
  await page.getByLabel(/^Telefon raqami/).fill("90 123-45-67");
  await page.getByRole("button", { name: "Kod yuborish" }).click();
  await expect(page.getByRole("heading", { name: "Kodni kiriting" })).toBeVisible();
  await expect(page.getByText(/\+998 90 123 45 67 raqamiga/)).toBeVisible();
  await page.getByLabel("Telegramʼdagi kod").fill(GOOD_CODE); // 6 raqamda o'zi yuboriladi
  await expect(page.getByRole("heading", { level: 1, name: "SellerMax" })).toBeVisible();
  await expect(page).toHaveURL("/");
  expect(api.bodies("POST", "/auth/otp")).toEqual([{ phone: PHONE }]);
  expect(api.bodies("POST", "/auth/login")).toEqual([{ phone: PHONE, code: GOOD_CODE }]);
});

test("noto'g'ri kod: xato matni, maydon tozalanadi; to'g'ri kod bilan davom etadi", async ({ page }) => {
  await mockApi(page, { me: null });
  await open(page, "/login");
  await page.getByLabel(/^Telefon raqami/).fill(PHONE);
  await page.getByRole("button", { name: "Kod yuborish" }).click();
  const code = page.getByLabel("Telegramʼdagi kod");
  await code.fill("000000");
  await expect(page.getByRole("alert")).toContainText("Kod notoʻgʻri");
  await expect(code).toHaveValue("");
  await expect(code).toBeFocused();
  await code.fill(GOOD_CODE);
  await expect(page).toHaveURL("/");
});

test("kirmagan foydalanuvchi himoyalangan sahifaga: kirgach o'sha sahifaga qaytadi", async ({ page }) => {
  await mockApi(page, { me: null });
  await open(page, "/pnl?cmp=previous");
  await expect(page).toHaveURL(/\/login\?redirect=/);
  await page.getByLabel(/^Telefon raqami/).fill(PHONE);
  await page.getByRole("button", { name: "Kod yuborish" }).click();
  await page.getByLabel("Telegramʼdagi kod").fill(GOOD_CODE);
  await expect(page.getByRole("heading", { level: 1, name: "Foyda" })).toBeVisible();
  await expect(page).toHaveURL(/\/pnl\?cmp=previous/);
});

test("begona manzilga qaytarish yo'q (ochiq qayta yo'naltirish)", async ({ page }) => {
  await mockApi(page, { me: null });
  await open(page, "/login?redirect=//evil.example");
  await page.getByLabel(/^Telefon raqami/).fill(PHONE);
  await page.getByRole("button", { name: "Kod yuborish" }).click();
  await page.getByLabel("Telegramʼdagi kod").fill(GOOD_CODE);
  await expect(page).toHaveURL("/");
  expect(new URL(page.url()).hostname).toBe("localhost");
});

test("til: tanlov saqlanadi (qayta yuklasa ham), kirishda profilga yoziladi", async ({ page }) => {
  const api = await mockApi(page, { me: null });
  await open(page, "/login");
  await page.getByLabel("Til").selectOption("ru");
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
  await page.getByLabel(/^Номер телефона/).fill(PHONE);
  await page.getByRole("button", { name: "Отправить код" }).click();
  await page.getByLabel("Код из Telegram").fill(GOOD_CODE);
  await expect(page).toHaveURL("/");
  await expect.poll(() => api.bodies("PATCH", "/auth/me")).toEqual([{ language: "ru" }]);
});
