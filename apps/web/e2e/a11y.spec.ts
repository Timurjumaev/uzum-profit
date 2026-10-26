// Kirish imkoniyati (04 §11, B3 chiqish mezoni: axe — jiddiy xato 0) HAQIQIY brauzerda: kontrast ham tekshiriladi
// (jsdom'da o'lchanmaydi). Asosiy sahifalar × yorug'/qorong'i × desktop/mobil.
import { expect, test, type Page } from "@playwright/test";

import { loadingSync, mockApi, NEW_USER, SHOPS, type ApiState } from "./support/api";
import { seriousViolations } from "./support/axe";
import { open } from "./support/page";

const fresh = SHOPS.map((s) => ({ ...s, alias: null, color: null, history_status: null }));

type Case = { name: string; path: string; state?: Partial<ApiState>; prepare?: (page: Page) => Promise<void> };

const CASES: Case[] = [
  { name: "kirish: telefon", path: "/login", state: { me: null } },
  {
    name: "kirish: kod",
    path: "/login",
    state: { me: null },
    prepare: async (page) => {
      await page.getByLabel(/^Telefon raqami/).fill("+998901234567");
      await page.getByRole("button", { name: "Kod yuborish" }).click();
      await page.getByRole("heading", { name: "Kodni kiriting" }).waitFor();
    },
  },
  { name: "onboarding: tashkilot", path: "/onboarding", state: { me: NEW_USER } },
  { name: "onboarding: kalit", path: "/onboarding", state: { shops: [] } },
  { name: "onboarding: do'konlar", path: "/onboarding?step=shops", state: { shops: fresh, sync: loadingSync(fresh) } },
  { name: "onboarding: tarix", path: "/onboarding?step=history", state: { shops: fresh, sync: loadingSync(fresh) } },
  { name: "bosh sahifa (karkas)", path: "/" },
  { name: "Foyda va zarar", path: "/pnl" },
  { name: "Foyda va zarar: SKU", path: "/pnl?view=sku" },
  { name: "Maʼlumotlar holati", path: "/status" },
  { name: "UI-kit", path: "/ui-kit" },
];

for (const scheme of ["light", "dark"] as const) {
  for (const c of CASES) {
    test(`${c.name} — ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockApi(page, c.state);
      await open(page, c.path);
      if (c.path === "/ui-kit") await page.waitForSelector(".chart__canvas svg path", { state: "attached" });
      await c.prepare?.(page);
      expect(await seriousViolations(page)).toEqual([]);
    });
  }
}

test("ochiq qatlamlar: Ctrl+K palitrasi, sinxron paneli, foydalanuvchi menyusi", async ({ page }) => {
  await mockApi(page);
  await open(page, "/");
  await page.getByRole("button", { name: "Tez oʻtish" }).click();
  await expect(page.getByRole("dialog", { name: "Tez oʻtish" })).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Maʼlumot yangiligi:/ }).click();
  expect(await seriousViolations(page)).toEqual([]);
});
