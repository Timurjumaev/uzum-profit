// Uzum qabulidagi farq (TM7, ADR-061 §8): kam qabul — "Uzum yo'qotdi" / "Men sanashda adashganman", ko'p qabul — "Topildi"
// (ochiq kamomad bo'lsa) yoki "Sonni oshirish"; kamomad holatlari va kompensatsiya; bog'liq jarima. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import type { Receiving, ReceivingDiff, Shortage } from "../../lib/api/types";
import { json, ME, ME_ROUTE, mockApi, type Routes } from "../../test/api";

const ORG = ME.orgs[0]!.id;
const SKU_A = "a1111111-1111-4111-8111-111111111111";
const SKU_B = "a2222222-2222-4222-8222-222222222222";
const SKU_C = "a3333333-3333-4333-8333-333333333333";
const D1 = "d1111111-1111-4111-8111-111111111111";
const S1 = "e1111111-1111-4111-8111-111111111111";
const S2 = "e2222222-2222-4222-8222-222222222222";
const GET_ROUTE = `GET /api/v1/orgs/${ORG}/receiving`;
const RESOLVE_ROUTE = `POST /api/v1/orgs/${ORG}/receiving/resolve`;
const PREVIEW_ROUTE = `GET /api/v1/orgs/${ORG}/receiving/preview`;

const diff = (over: Partial<ReceivingDiff>): ReceivingDiff => ({
  dispatch_id: D1,
  invoice_id: "i1",
  invoice_number: 18324,
  shop: "byDurii",
  accepted_on: "2026-11-12",
  sku_id: SKU_A,
  title: "Mashina-Qizil",
  barcode: "4780000000001",
  shipped: 10,
  accepted: 8,
  diff: -2,
  unit_cost: "10000.00",
  value: "20000.00",
  resolution: null,
  shortage_id: null,
  open_shortages: 0,
  fines: [{ day: "2026-11-12", amount: "7000.00" }],
  fines_total: "7000.00",
  ...over,
});
const shortage = (over: Partial<Shortage>): Shortage => ({
  id: S1,
  dispatch_id: D1,
  sku_id: SKU_C,
  title: "Kamar-L",
  shop: "byDurii",
  qty: 3,
  status: "open",
  unit_cost: "5000.00",
  amount: "15000.00",
  compensation: null,
  loss: null,
  closed_on: null,
  note: null,
  created_on: "2026-11-05",
  claim_until: "2026-12-12",
  ...over,
});
const data = (over: Partial<Receiving> = {}): Receiving => ({
  diffs: [diff({}), diff({ sku_id: SKU_B, title: "Koʻylak-Oq", shipped: 5, accepted: 6, diff: 1, value: "10000.00", fines: [], fines_total: null }), diff({ sku_id: SKU_C, title: "Kamar-L", shipped: 4, accepted: 5, diff: 1, open_shortages: 3, fines: [], fines_total: null })],
  shortages: [shortage({}), shortage({ id: S2, title: "Soat", status: "written_off", loss: "8000.00", closed_on: "2026-11-10" })],
  amounts: true,
  progress: [],
  ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [GET_ROUTE]: () => json(200, data()),
    [RESOLVE_ROUTE]: () => json(200, data()),
    [PREVIEW_ROUTE]: () => json(200, { lines: [{ purchase_id: "p1", purchase_title: "Oktabr partiyasi", line_id: "l1", qty_before: 10, qty_after: 8, unit_cost_before: "10000.00", unit_cost_after: "12500.00" }] }),
    [`PATCH /api/v1/orgs/${ORG}/receiving/shortages/${S1}`]: () => json(200, data()),
    [`PATCH /api/v1/orgs/${ORG}/receiving/shortages/${S2}`]: () => json(200, data()),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/receiving"] }), "uz-Latn")} />);
  return api;
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("Uzum qabulidagi farq", () => {
  it("farqlar: kam — ikki tanlov, ko'p — Topildi yoki Sonni oshirish; summa va jarima", async () => {
    const api = await renderAt();
    const list = await screen.findByRole("list", { name: "Qabul farqlari" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]!).getByText("2 dona kam")).toBeTruthy();
    expect(within(items[0]!).getByText(/Joʻnatildi 10 · qabul qilindi 8/)).toBeTruthy();
    expect(within(items[0]!).getByText(/Bogʻliq jarima: 1 ta/)).toBeTruthy();
    expect(within(items[1]!).getByText("1 dona koʻp")).toBeTruthy();
    expect(within(items[1]!).getByRole("button", { name: "Sonni oshirish: Koʻylak-Oq" })).toBeTruthy();
    expect(within(items[2]!).getByText(/ochiq kamomad: 3 dona/)).toBeTruthy();
    fireEvent.click(within(items[0]!).getByRole("button", { name: "Men sanashda adashganman: Mashina-Qizil" }));
    // TM9.2: oqibat oldindan — tasdiqlanmaguncha yuborilmaydi.
    const preview = await within(items[0]!).findByRole("group", { name: "Nima oʻzgaradi" });
    await within(preview).findByText(/Oktabr partiyasi: soni 10 → 8/);
    expect(preview.textContent).toMatch(/tannarx 10\D000\Dsoʻm → 12\D500\Dsoʻm/);
    expect(bodiesOf(api, RESOLVE_ROUTE)).toEqual([]);
    fireEvent.click(within(preview).getByRole("button", { name: "Tasdiqlash" }));
    await waitFor(() => expect(bodiesOf(api, RESOLVE_ROUTE)).toEqual([{ dispatch_id: D1, sku_id: SKU_A, action: "miscount" }]));
    expect(await screen.findByText(/Xarid soni tuzatildi/)).toBeTruthy();
    fireEvent.click(within(items[2]!).getByRole("button", { name: "Topildi: Kamar-L" }));
    await waitFor(() => expect(bodiesOf(api, RESOLVE_ROUTE)[1]).toEqual({ dispatch_id: D1, sku_id: SKU_C, action: "found" }));
    fireEvent.click(within(items[0]!).getByRole("button", { name: "Uzum yoʻqotdi: Mashina-Qizil" }));
    await waitFor(() => expect(bodiesOf(api, RESOLVE_ROUTE)[2]).toMatchObject({ action: "lost" }));
  });

  it("kamomad: holatlar, kompensatsiya summasi, zarar va qayta ochish", async () => {
    const p1 = `PATCH /api/v1/orgs/${ORG}/receiving/shortages/${S1}`;
    const p2 = `PATCH /api/v1/orgs/${ORG}/receiving/shortages/${S2}`;
    const api = await renderAt();
    await screen.findByRole("list", { name: "Kamomad roʻyxati" });
    const list = { get: () => screen.getByRole("list", { name: "Kamomad roʻyxati" }) };
    expect(within(list.get()).getByText("Ochiq")).toBeTruthy();
    expect(within(list.get()).getByText(/Uzumga daʼvo muddati: 12.12.2026 gacha/)).toBeTruthy();
    expect(within(list.get()).getByText("Zarar deb yopildi")).toBeTruthy();
    expect(within(list.get()).getByText(/Foyda hisobidagi zarar/)).toBeTruthy();
    fireEvent.click(within(list.get()).getByRole("button", { name: "Kompensatsiya qilindi: Kamar-L" }));
    const save = () => within(list.get()).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save().disabled).toBe(true);
    fireEvent.change(within(list.get()).getByLabelText("Kompensatsiya summasi: Kamar-L"), { target: { value: "12000" } });
    fireEvent.click(save());
    await waitFor(() => expect(bodiesOf(api, p1)).toEqual([{ status: "compensated", compensation: "12000" }]));
    expect(await screen.findByText("Kamomad holati saqlandi")).toBeTruthy();
    fireEvent.click(within(list.get()).getByRole("button", { name: "Qayta ochish: Soat" }));
    await waitFor(() => expect(bodiesOf(api, p2)).toEqual([{ status: "open" }]));
  });

  it("buxgalter: amallarsiz; bo'sh holatlar; qaror yozilgan farq belgisi", async () => {
    await renderAt({ [GET_ROUTE]: () => json(200, data({ diffs: [diff({ resolution: "lost" })] })) }, "accountant");
    const list = await screen.findByRole("list", { name: "Qabul farqlari" });
    expect(within(list).getByText("Uzum yoʻqotdi")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Uzum yoʻqotdi:/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Qayta ochish/ })).toBeNull();
    cleanup();
    await renderAt({ [GET_ROUTE]: () => json(200, { diffs: [], shortages: [], amounts: true, progress: [] }) });
    expect(await screen.findByText("Farq yoʻq")).toBeTruthy();
    expect(screen.getByText("Kamomad yoʻq")).toBeTruthy();
  });

  it("qabul davom etmoqda (TM9.2): 719 / 744, farq sanasi", async () => {
    await renderAt({ [GET_ROUTE]: () => json(200, data({ progress: [{ dispatch_id: "d9", invoice_id: "i9", invoice_number: 18400, accepted_on: "2026-11-15", accepted: 719, declared: 744, until: "2026-11-22" }] })) });
    const list = await screen.findByRole("list", { name: "Qabul davom etmoqda" });
    expect(list.textContent).toMatch(/719 \/ 744 qabul qilindi · farq 22\.11\.2026 dan/);
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt();
    await screen.findByRole("list", { name: "Kamomad roʻyxati" });
    const results = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
