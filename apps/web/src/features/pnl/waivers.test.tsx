// Uzum bonuslari P&L sahifasida (B4.2a, ADR-031): banner (haqiqiy hisob o'zgarmaydi), tizim taklifini belgilash /
// rad etish, qo'shish shakli (API'ga to'g'ri tana), o'chirish, ruxsatlar (faqat ega va menejer o'zgartiradi),
// drill-down'dagi "Bonus davri" belgisi va bosh sahifa grafigidagi soya. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import {
  dashboardData,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  PNL_ROUTE,
  pnlData,
  problem,
  SALES_ROUTE,
  SHOP_B,
  WAIVER_CREATE_ROUTE,
  waiverDeleteRoute,
  WAIVERS_ROUTE,
  type Routes,
} from "../../test/api";
import { waiver } from "../../test/pnl";
import { bonusBands } from "../home/Blocks";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const PATH = "/pnl?from=2026-09-01&to=2026-10-31";
const KINDS = ["sale_logistics", "advertising", "storage", "return_storage"];
const suggestion = { shop_id: SHOP_B, start_on: "2026-10-05", end_on: "2026-10-06", kinds: ["sale_logistics"] };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function renderPnl(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [PNL_ROUTE]: () => json(200, pnlData({ waivers: [waiver()], waiver_suggestions: [suggestion] })),
    [WAIVERS_ROUTE]: () => json(200, { items: [waiver()], kinds: KINDS }),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: [PATH] }), "uz-Latn")} />);
  await screen.findByRole("table", { name: "Foyda va zarar: tushumdan sof foydagacha" });
  return api;
}

const banner = (title: RegExp) => screen.getByText(title).closest(".ui-banner") as HTMLElement;

describe("bonus banneri", () => {
  it("davr, do'kon, bepul turlar va sabab; haqiqiy hisob o'zgarmasligi aytiladi", async () => {
    await renderPnl();
    const b = banner(/^Uzum bonusi: Uzum nosozligi uchun kompensatsiya/);
    expect(b.className).toContain("ui-tone--info");
    expect(norm(b.textContent!)).toContain(
      norm(`${f.period("2026-10-10", "2026-10-31")}, hamma doʻkon — bepul: Sotuv logistikasi, Saqlash. Shu xarajatlar 0 boʻlib qoladi, haqiqiy foyda oʻzgarmaydi.`),
    );
  });

  it("sababsiz va bitta do'kon uchun", async () => {
    await renderPnl({ [PNL_ROUTE]: () => json(200, pnlData({ waivers: [waiver({ reason: "", shop_id: SHOP_B, kinds: ["return_storage"] })] })) });
    const b = banner(/sababi yozilmagan/);
    expect(norm(b.textContent!)).toContain("EL-ONE — bepul: Qaytim saqlash.");
  });

  it("o'chirish: DELETE so'rovi, hisobotlar qayta so'raladi", async () => {
    const api = await renderPnl({ [waiverDeleteRoute("w-1")]: () => new Response(null, { status: 204 }) });
    const before = api.count(`GET ${PNL_ROUTE.split(" ")[1]}`);
    fireEvent.click(within(banner(/^Uzum bonusi:/)).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.count(waiverDeleteRoute("w-1"))).toBe(1));
    await waitFor(() => expect(api.count(`GET ${PNL_ROUTE.split(" ")[1]}`)).toBeGreaterThan(before));
    expect(await screen.findByText("Bonus davri oʻchirildi")).toBeTruthy();
  });

  it("buxgalter: ko'radi, lekin o'zgartira olmaydi (tugmalar yo'q)", async () => {
    await renderPnl({}, "accountant");
    expect(banner(/^Uzum bonusi:/)).toBeTruthy();
    expect(screen.getByText("Uzum logistikani olmagan koʻrinadi")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Oʻchirish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Bonus deb belgilash" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Uzum bonusini qoʻshish" })).toBeNull();
  });
});

describe("tizim taklifi", () => {
  it("'Bonus deb belgilash' — shakl taklif bilan to'ladi, saqlansa source=detected", async () => {
    const api = await renderPnl({ [WAIVER_CREATE_ROUTE]: () => json(201, waiver({ id: "w-2" })) });
    const s = banner(/Uzum logistikani olmagan/);
    expect(s.className).toContain("ui-tone--warning");
    expect(norm(s.textContent!)).toContain(norm(`EL-ONE, ${f.period("2026-10-05", "2026-10-06")}`));
    fireEvent.click(within(s).getByRole("button", { name: "Bonus deb belgilash" }));
    const dlg = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    expect((within(dlg).getByLabelText("Doʻkon") as HTMLSelectElement).value).toBe(SHOP_B);
    expect((within(dlg).getByLabelText("Boshlanish") as HTMLInputElement).value).toBe("2026-10-05");
    expect((within(dlg).getByLabelText("Sotuv logistikasi") as HTMLInputElement).checked).toBe(true);
    fireEvent.change(within(dlg).getByLabelText(/^Sabab/), { target: { value: "Nosozlik" } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.bodiesOf(WAIVER_CREATE_ROUTE)).toEqual([
      { shop_id: SHOP_B, start_on: "2026-10-05", end_on: "2026-10-06", kinds: ["sale_logistics"], reason: "Nosozlik", source: "detected", dismissed: false },
    ]);
    expect(await screen.findByText("Bonus davri saqlandi")).toBeTruthy();
  });

  it("'Yo'q, bonus emas' — rad etilgan yozuv (dismissed), qayta so'ralmaydi", async () => {
    const api = await renderPnl({ [WAIVER_CREATE_ROUTE]: () => json(201, waiver({ id: "w-3", dismissed: true })) });
    fireEvent.click(within(banner(/Uzum logistikani olmagan/)).getByRole("button", { name: "Yoʻq, bonus emas" }));
    await waitFor(() => expect(api.bodiesOf(WAIVER_CREATE_ROUTE)).toHaveLength(1));
    expect(api.bodiesOf(WAIVER_CREATE_ROUTE)[0]).toEqual({ ...suggestion, reason: "", source: "detected", dismissed: true });
    expect(await screen.findByText(/Taklif yopildi/)).toBeTruthy();
  });
});

describe("qo'shish shakli", () => {
  it("hamma do'kon, tanlangan davr, turlar API'dan; xato — shakl ichida matn bilan", async () => {
    const api = await renderPnl({
      [WAIVER_CREATE_ROUTE]: [() => problem(422, "bad_kinds"), () => json(201, waiver({ id: "w-4" }))],
    });
    fireEvent.click(screen.getByRole("button", { name: "Uzum bonusini qoʻshish" }));
    const dlg = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    expect((within(dlg).getByLabelText("Doʻkon") as HTMLSelectElement).value).toBe("");
    expect((within(dlg).getByLabelText("Tugash") as HTMLInputElement).value).toBe("2026-10-31");
    expect(await within(dlg).findByLabelText("Qaytim saqlash")).toBeTruthy(); // turlar ro'yxati API'dan
    fireEvent.click(within(dlg).getByLabelText("Sotuv logistikasi")); // olib tashlandi — tur yo'q
    fireEvent.click(within(dlg).getByRole("button", { name: "Bonusni saqlash" }));
    expect(await within(dlg).findByText("Kamida bitta bepul xarajat turini tanlang.")).toBeTruthy();
    fireEvent.click(within(dlg).getByLabelText("Saqlash"));
    fireEvent.click(within(dlg).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [, second] = api.bodiesOf(WAIVER_CREATE_ROUTE) as Array<Record<string, unknown>>;
    expect(second).toMatchObject({ shop_id: null, start_on: "2026-09-01", end_on: "2026-10-31", kinds: ["storage"], source: "manual" });
  });

  it("Bekor qilish — so'rovsiz yopiladi; axe: jiddiy xato 0", async () => {
    const api = await renderPnl();
    fireEvent.click(screen.getByRole("button", { name: "Uzum bonusini qoʻshish" }));
    const dlg = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    await within(dlg).findByLabelText("Qaytim saqlash");
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
    fireEvent.click(within(dlg).getByRole("button", { name: "Bekor qilish" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.count(WAIVER_CREATE_ROUTE)).toBe(0);
  }, 30_000);
});

describe("belgi va grafik", () => {
  it("drill-down: bonus davridagi sotuv — 'Bonus davri' belgisi", async () => {
    const sale = (id: string, waiver_id: string | null) => ({
      id, shop_id: SHOP_B, sku_id: "k1", sku_title: `SKU ${id}`, order_id: 1, external_id: 1, ordered_at: "2026-10-12T07:00:00Z", day: "2026-10-12",
      status: "TO_WITHDRAW", group: "completed", amount: 1, amount_returns: 0, return_cause: null, sell_price: "100000.00", revenue: "100000.00",
      commission: "20000.00", logistics: "0.00", payout: "80000.00", cogs: "40000.00", gross_profit: "40000.00", cost_flags: [], recalculated_at: null,
      previous_cogs: null, waiver_id,
    });
    await renderPnl({
      [SALES_ROUTE]: () => json(200, { meta: pnlData().meta, items: [sale("a", "w-1"), sale("b", null)], next_cursor: null, summary: { units: 2, canceled: 0, returns: 0, cancel_share: null, return_share: null } }),
    });
    fireEvent.click(screen.getByRole("button", { name: "Tushum" }));
    const dlg = await screen.findByRole("dialog", { name: "Tushum" });
    const rowA = (await within(dlg).findByText("SKU a")).closest("tr")!;
    expect(within(rowA).getByText("Bonus davri")).toBeTruthy();
    expect(within(within(dlg).getByText("SKU b").closest("tr")!).queryByText("Bonus davri")).toBeNull();
  });

  it("bosh sahifa grafigi: bonus davri soya, davr chegarasiga qisqartiriladi", () => {
    const data = dashboardData({ waivers: [waiver({ start_on: "2026-09-20", end_on: "2026-11-05" }), waiver({ id: "w-2", reason: "" })] });
    expect(bonusBands(data, "Uzum bonusi")).toEqual([
      { from: "2026-10-01", to: "2026-10-26", kind: "shade", label: "Uzum nosozligi uchun kompensatsiya" },
      { from: "2026-10-10", to: "2026-10-26", kind: "shade", label: "Uzum bonusi" },
    ]);
  });
});
