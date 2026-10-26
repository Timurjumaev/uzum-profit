// Onboarding (M2): yangi foydalanuvchi — kirish → tashkilot → Uzum kaliti → do'konlar → tarix → bosh sahifa.
import { expect, test } from "@playwright/test";

import { GOOD_CODE, GOOD_KEY, loadingSync, mockApi, NEW_USER, ORG_ID, PHONE, SHOP_A, SHOP_B, SHOPS } from "./support/api";
import { open } from "./support/page";

const fresh = SHOPS.map((s) => ({ ...s, alias: null, color: null, history_status: null }));

test("yangi foydalanuvchining to'liq yo'li", async ({ page }) => {
  const api = await mockApi(page, {
    me: null,
    orgsOnLogin: [],
    afterConnect: { shops: fresh, sync: loadingSync(fresh) },
  });
  await open(page, "/login");
  await page.getByLabel(/^Telefon raqami/).fill(PHONE);
  await page.getByRole("button", { name: "Kod yuborish" }).click();
  await page.getByLabel("Telegramʼdagi kod").fill(GOOD_CODE);

  // 1. tashkilot
  await expect(page.getByRole("heading", { level: 2, name: "Biznesingiz nomi" })).toBeVisible();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel(/^Tashkilot nomi/).fill("byDurii");
  await page.getByRole("button", { name: "Davom etish" }).click();

  // 2. Uzum kaliti: avval noto'g'ri, keyin to'g'ri
  await expect(page.getByRole("heading", { level: 2, name: "Uzum API kaliti" })).toBeVisible();
  const key = page.getByLabel(/^API kalit/);
  await expect(key).toHaveAttribute("type", "password");
  await key.fill("noto'g'ri-kalit-123");
  await page.getByRole("button", { name: "Kalitni tekshirish va ulash" }).click();
  await expect(page.getByRole("alert")).toContainText("Uzum kalitni rad etdi");
  await key.fill(GOOD_KEY);
  await page.getByRole("button", { name: "Kalitni tekshirish va ulash" }).click();

  // 3. do'konlar: nom va rang
  await expect(page.getByRole("heading", { level: 2, name: "Doʻkonlarni tanlang" })).toBeVisible();
  expect(page.url()).not.toContain(GOOD_KEY);
  const second = page.getByRole("listitem").filter({ hasText: "EL-ONE" });
  await second.getByLabel(/^Qisqa nom/).fill("Elone");
  await second.getByRole("radio", { name: "Qizil" }).check({ force: true });
  await page.getByRole("button", { name: "Davom etish" }).click();

  // 4. tarix: progress, kutmasdan o'tish
  await expect(page.getByRole("heading", { level: 2, name: "Tarix yuklanmoqda" })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Sotuvlar" }).first()).toHaveAttribute("aria-valuenow", "1830");
  await page.getByRole("button", { name: "Kutmasdan bosh sahifaga oʻtish" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^Sof foyda/ })).toBeVisible();
  await expect(page).toHaveURL("/");

  expect(api.bodies("POST", "/orgs")).toEqual([{ name: "byDurii", inn: null }]);
  expect(api.bodies("POST", `/orgs/${ORG_ID}/accounts`)).toEqual([{ token: "noto'g'ri-kalit-123" }, { token: GOOD_KEY }]);
  expect(api.bodies("PATCH", `/orgs/${ORG_ID}/shops/${SHOP_A}`)).toEqual([{ color: "#2A78D6" }]); // standart 1-rang
  expect(api.bodies("PATCH", `/orgs/${ORG_ID}/shops/${SHOP_B}`)).toEqual([{ alias: "Elone", color: "#E34948" }]);
});

test("to'xtab, keyin davom etish: do'konlar bor — do'konlar qadamidan boshlanadi; chiqish ishlaydi", async ({ page }) => {
  const api = await mockApi(page, { shops: fresh, sync: loadingSync(fresh) });
  await open(page, "/onboarding");
  await expect(page.getByRole("heading", { level: 2, name: "Doʻkonlarni tanlang" })).toBeVisible();
  await page.getByRole("button", { name: "Chiqish" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(api.bodies("POST", "/auth/logout")).toEqual([null]);
});

test("URL'dagi oldinga sakrash e'tiborga olinmaydi (tashkilot yo'q — tashkilot qadami)", async ({ page }) => {
  await mockApi(page, { me: NEW_USER });
  await open(page, "/onboarding?step=history");
  await expect(page.getByRole("heading", { level: 2, name: "Biznesingiz nomi" })).toBeVisible();
});
