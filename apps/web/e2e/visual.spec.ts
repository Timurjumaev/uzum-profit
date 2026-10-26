// Vizual regressiya (03 §14): asosiy sahifalar skrinshotlari — yorug'/qorong'i × 1440/390 px. Baza (baseline) repoda
// (`e2e/__screenshots__`); yangilash: `pnpm --filter web e2e:update` va farqni ko'zdan kechirib commit qilish.
// Vaqt qotirilgan, animatsiya o'chiq, tarmoq — soxta: farq faqat haqiqiy o'zgarishdan chiqadi.
import { expect, test, type Page } from "@playwright/test";

import { loadingSync, mockApi, NEW_USER, SHOPS, type ApiState } from "./support/api";
import { open } from "./support/page";

const fresh = SHOPS.map((s) => ({ ...s, alias: null, color: null, history_status: null }));

type Shot = { name: string; path: string; state?: Partial<ApiState>; prepare?: (page: Page) => Promise<void>; full?: boolean };

const SHOTS: Shot[] = [
  { name: "login", path: "/login", state: { me: null } },
  {
    name: "login-code",
    path: "/login",
    state: { me: null },
    prepare: async (page) => {
      await page.getByLabel(/^Telefon raqami/).fill("+998901234567");
      await page.getByRole("button", { name: "Kod yuborish" }).click();
      await page.getByRole("heading", { name: "Kodni kiriting" }).waitFor();
    },
  },
  { name: "onboarding-org", path: "/onboarding", state: { me: NEW_USER } },
  { name: "onboarding-key", path: "/onboarding", state: { shops: [] } },
  { name: "onboarding-shops", path: "/onboarding?step=shops", state: { shops: fresh, sync: loadingSync(fresh) } },
  { name: "onboarding-history", path: "/onboarding?step=history", state: { shops: fresh, sync: loadingSync(fresh) } },
  { name: "home", path: "/" },
  { name: "status", path: "/status" },
  {
    name: "palette",
    path: "/",
    prepare: async (page) => {
      await page.getByRole("button", { name: "Tez oʻtish" }).click();
      await page.getByRole("dialog", { name: "Tez oʻtish" }).waitFor();
    },
  },
  {
    name: "ui-kit",
    path: "/ui-kit",
    full: true,
    prepare: async (page) => {
      await page.waitForSelector(".chart__canvas svg path", { state: "attached" });
      await page.waitForTimeout(300);
    },
  },
];

for (const scheme of ["light", "dark"] as const) {
  for (const shot of SHOTS) {
    test(`${shot.name} — ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockApi(page, shot.state);
      await open(page, shot.path);
      await shot.prepare?.(page);
      await expect(page).toHaveScreenshot(`${shot.name}-${scheme}.png`, { fullPage: shot.full ?? true });
    });
  }
}
