// Ta'minot oqimi to'liq (TM8, ADR-061): xarid → kargo puli → sanash → Uzumga jo'natish → qabul farqi. Soxta API ustida:
// har qadamda sahifadan keyingisiga o'tiladi va API'ga to'g'ri so'rov ketgani tekshiriladi.
import { expect, test } from "@playwright/test";

import { PURCHASE_1 } from "../src/test/purchases";
import { mockApi, ORG_ID } from "./support/api";
import { open } from "./support/page";

test("ta'minot oqimi: xarid → kargo puli → sanash → jo'natish → qabul farqi", async ({ page }) => {
  const api = await mockApi(page);
  const posted = (path: string) => api.requests.filter((r) => r.method === "POST" && r.path === `/orgs/${ORG_ID}/${path}`).map((r) => r.body as Record<string, unknown>);

  // 1. Yangi xarid → xarid sahifasi.
  await open(page, "/purchases");
  await page.getByRole("button", { name: "Yangi xarid" }).first().click();
  const quick = page.getByRole("dialog", { name: "Yangi xarid (partiya)" });
  await quick.getByRole("combobox", { name: "Tovarlar" }).click();
  await quick.getByRole("listbox").getByRole("option").first().click();
  await quick.getByLabel("Dona").fill("100");
  await quick.getByLabel(/^Jami toʻlandi/).fill("1000");
  await quick.getByRole("button", { name: "Xaridni saqlash" }).click();
  await expect(page).toHaveURL(new RegExp(`/purchases/${PURCHASE_1}$`));
  expect(posted("purchases/quick")).toHaveLength(1);
  expect(posted("purchases/quick")[0]).toMatchObject({ paid_amount: "1000" });

  // 2. Kargo puli.
  await open(page, "/cargo-pool");
  await page.getByLabel("Kargo puli: Oktabr partiyasi").fill("45");
  await page.getByRole("button", { name: "Kargo pulini saqlash (1)" }).click();
  await expect.poll(() => posted("cargo-pool/tracked").length).toBe(1);

  // 3. Sanash.
  await open(page, `/purchases/${PURCHASE_1}`);
  await page.getByRole("button", { name: "Sanash" }).click();
  const count = page.getByRole("dialog", { name: "Sanash" });
  await count.getByRole("button", { name: "Hammasi keldi" }).click();
  await count.getByRole("button", { name: "Sanashni saqlash" }).click();
  await expect.poll(() => posted(`purchases/${PURCHASE_1}/count`).length).toBe(1);

  // 4. Omborim → Uzumga jo'natish → Excel.
  await open(page, "/warehouse");
  await page.getByRole("link", { name: "Uzumga joʻnatish" }).click();
  await expect(page).toHaveURL(/\/dispatches$/);
  await page.getByRole("button", { name: /^Excel yuklab olish \(\d+ dona\)$/ }).click();
  await expect.poll(() => posted("dispatches").length).toBe(1);

  // 5. Qabul farqi → "Uzum yo'qotdi".
  await page.getByRole("link", { name: "Qabul farqi" }).click();
  await expect(page).toHaveURL(/\/receiving$/);
  await page.getByRole("button", { name: "Uzum yoʻqotdi: AIRGILOF-RANG-1" }).click();
  await expect.poll(() => posted("receiving/resolve")).toEqual([{ dispatch_id: "d0000002-0000-4000-8000-000000000000", sku_id: "a0000001-0000-4000-8000-000000000000", action: "lost" }]);
  await expect(page.getByText("Kamomad roʻyxatiga qoʻshildi")).toBeVisible();
});
