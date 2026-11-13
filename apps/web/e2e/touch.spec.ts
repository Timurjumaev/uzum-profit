// Telefonda bosish maydoni ≥ 44 px (04 §11, audit D4; B4.75 PR-4): hamma asosiy sahifa va karkas, 360 px.
// Matn ichidagi havola (gap ichida, `p a`) WCAG 2.5.8 istisnosi — sanalmaydi.
import { expect, test } from "@playwright/test";

import { PURCHASE_1 } from "../src/test/purchases";
import { SHIPMENT_1 } from "../src/test/shipments";
import { mockApi } from "./support/api";
import { open } from "./support/page";

const PAGES = ["/", "/pnl", "/products", "/orders", "/expenses", "/purchases", `/purchases/${PURCHASE_1}`, "/cargo-pool", "/warehouse", "/dispatches", "/receiving", "/shipments", `/shipments/${SHIPMENT_1}`, "/inventory", "/settings", "/opening", "/status"];

test.use({ viewport: { width: 360, height: 800 }, hasTouch: true });

for (const path of PAGES) {
  test(`bosish maydoni ≥ 44 px (360 px) ${path}`, async ({ page }) => {
    await mockApi(page);
    await open(page, path);
    await page.getByRole("heading", { level: 1 }).first().waitFor();
    await page.waitForLoadState("networkidle");
    const small = await page.evaluate(() =>
      [...document.querySelectorAll("a,button,select,input:not([type=hidden]),[role=tab],summary")]
        .filter((e) => !e.closest("p") && !e.closest("[aria-hidden=true]"))
        // Belgilash katagi / radio label ichida — bosish maydoni label'ning o'zi.
        .map((e) => ({ name: (e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 40), box: (e.closest("label") ?? e).getBoundingClientRect(), style: getComputedStyle(e) }))
        // Ekrandan tashqaridagi (fokusda chiqadigan "Asosiy kontentga o'tish") hisoblanmaydi.
        .filter((x) => x.style.visibility !== "hidden" && x.box.bottom > 0 && x.box.width > 0 && x.box.height > 0 && (x.box.height < 43.5 || x.box.width < 43.5))
        .map((x) => `${x.name}: ${Math.round(x.box.width)}×${Math.round(x.box.height)}`),
    );
    expect(small).toEqual([]);
  });
}
