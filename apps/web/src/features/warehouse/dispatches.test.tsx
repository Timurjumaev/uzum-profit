// Uzumga jo'natish (TM6, ADR-061 §7): qoralama (to'liq son, kamaytirish, olib tashlash, shtrix-kodsiz SKU ogohlantirishi),
// saqlash + Excel yuklab olish, jo'natmalar ro'yxati (holat, nomzod postavkani tanlash, bekor qilish). Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import type { Dispatch, DispatchDraftRow } from "../../lib/api/types";
import { formatterFor } from "../../lib/format";
import { json, ME, ME_ROUTE, mockApi, SHOPS, type Routes } from "../../test/api";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");

const ORG = ME.orgs[0]!.id;
const SHOP = "b1111111-1111-4111-8111-111111111111";
const SKU_A = "a1111111-1111-4111-8111-111111111111";
const SKU_B = "a2222222-2222-4222-8222-222222222222";
const D1 = "d1111111-1111-4111-8111-111111111111";
const D2 = "d2222222-2222-4222-8222-222222222222";
const DRAFT_ROUTE = `GET /api/v1/orgs/${ORG}/dispatches/draft`;
const LIST_ROUTE = `GET /api/v1/orgs/${ORG}/dispatches`;
const CREATE_ROUTE = `POST /api/v1/orgs/${ORG}/dispatches`;
const ORPHANS_ROUTE = `GET /api/v1/orgs/${ORG}/dispatches/orphans`;

const draftRow = (over: Partial<DispatchDraftRow>): DispatchDraftRow => ({ sku_id: SKU_A, title: "Mashina-Qizil", product_title: "Mashina", barcode: "4780000000001", qty: 70, unit_cost: "10000.00", estimated: false, unknown: false, ...over });
const dispatch = (over: Partial<Dispatch>): Dispatch => ({
  id: D1,
  shop_id: SHOP,
  shop: "byDurii",
  status: "sending",
  exported_at: "2026-11-10T10:00:00Z",
  linked_at: null,
  canceled_at: null,
  note: null,
  units: 20,
  items: [{ sku_id: SKU_A, title: "Mashina-Qizil", barcode: "4780000000001", qty: 20, unit_cost: "10000.00" }],
  invoice: null,
  candidates: [],
  origin: "excel",
  adjustments: [],
  ...over,
});
const inv = (id: string, number: number) => ({ id, number, status: "CREATED", created_on: "2026-11-11T08:00:00Z", accepted: null });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [DRAFT_ROUTE]: () => json(200, { shop_id: SHOP, rows: [draftRow({}), draftRow({ sku_id: SKU_B, title: "Koʻylak-Oq", barcode: "4780000000002", qty: 5 })], no_barcode: [draftRow({ sku_id: "x", title: "Shtrixsiz", barcode: null, qty: 3 })] }),
    [LIST_ROUTE]: () =>
      json(200, {
        items: [
          dispatch({ id: D1, candidates: [inv("i1", 101), inv("i2", 102)] }),
          dispatch({ id: D2, status: "linked", invoice: inv("i9", 109), linked_at: "2026-11-11T09:00:00Z" }),
          dispatch({ id: "d3", status: "canceled", canceled_at: "2026-11-09T09:00:00Z" }),
        ],
      }),
    [ORPHANS_ROUTE]: () => json(200, { items: [] }),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/dispatches"] }), "uz-Latn")} />);
  return api;
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("Uzumga jo'natish", () => {
  it("qoralama: to'liq son, kamaytirish, olib tashlash; saqlash va Excel", async () => {
    const excel = `GET /api/v1/orgs/${ORG}/dispatches/${D1}/excel`;
    const api = await renderAt({
      [CREATE_ROUTE]: () => json(201, dispatch({})),
      [excel]: () => new Response(new Blob(["x"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="uzum-jonatma-2026-11-10.xlsx"' } }),
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const list = await screen.findByRole("list", { name: "Joʻnatiladigan SKUʼlar" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/Shtrix-kodi yoʻq 1 ta SKU/)).toBeTruthy();
    expect((screen.getByLabelText("Dona: Mashina-Qizil") as HTMLInputElement).value).toBe("70");
    fireEvent.change(screen.getByLabelText("Dona: Mashina-Qizil"), { target: { value: "71" } });
    expect((screen.getByRole("button", { name: /^Excel yuklab olish/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Dona: Mashina-Qizil"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Olib tashlash: Koʻylak-Oq" }));
    expect(screen.getByRole("button", { name: "Olib tashlanganlarni qaytarish (1)" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Excel yuklab olish (20 dona)" }));
    await waitFor(() => expect(bodiesOf(api, CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, CREATE_ROUTE)[0]).toEqual({ shop_id: SHOPS[0]!.id, items: [{ sku_id: SKU_A, qty: 20 }] });
    await waitFor(() => expect(api.count(excel)).toBe(1));
    expect(await screen.findByText(/Joʻnatma saqlandi/)).toBeTruthy();
  });

  it("F54: \"Tavsiya bo'yicha to'ldirish\" — reja miqdori qo'yiladi, reja 0 — olib tashlanadi, rejasiz — o'zgarmaydi; standart — to'liq son", async () => {
    const rows = [draftRow({ plan_qty: 25 }), draftRow({ sku_id: SKU_B, title: "Koʻylak-Oq", barcode: "4780000000002", qty: 5, plan_qty: 0 }), draftRow({ sku_id: "c", title: "Rejasiz", barcode: "4780000000003", qty: 9, plan_qty: null })];
    await renderAt({ [DRAFT_ROUTE]: () => json(200, { shop_id: SHOP, rows, no_barcode: [] }) });
    expect((await screen.findByLabelText("Dona: Mashina-Qizil") as HTMLInputElement).value).toBe("70"); // standart — to'liq
    fireEvent.click(screen.getByRole("button", { name: "Tavsiya boʻyicha toʻldirish" }));
    expect((screen.getByLabelText("Dona: Mashina-Qizil") as HTMLInputElement).value).toBe("25");
    expect(screen.queryByLabelText("Dona: Koʻylak-Oq")).toBeNull(); // Uzumda yetarli — olib tashlandi
    expect((screen.getByLabelText("Dona: Rejasiz") as HTMLInputElement).value).toBe("9");
    fireEvent.click(screen.getByRole("button", { name: "Olib tashlanganlarni qaytarish (1)" }));
    expect(screen.getByLabelText("Dona: Koʻylak-Oq")).toBeTruthy();
  });

  it("reja yo'q (maqsad qamrov sozlanmagan) — tugma ko'rinmaydi", async () => {
    await renderAt();
    await screen.findByLabelText("Dona: Mashina-Qizil");
    expect(screen.queryByRole("button", { name: "Tavsiya boʻyicha toʻldirish" })).toBeNull();
  });

  it("TM9.7: tannarx — taxminiy belgi, noma'lum bo'lsa kiritmasdan saqlanmaydi, kiritilgani yuboriladi", async () => {
    const api = await renderAt({
      [DRAFT_ROUTE]: () =>
        json(200, {
          shop_id: SHOP,
          rows: [draftRow({ estimated: true }), draftRow({ sku_id: SKU_B, title: "Koʻylak-Oq", barcode: "4780000000002", qty: 5, unit_cost: "0.00", unknown: true })],
          no_barcode: [],
        }),
      [CREATE_ROUTE]: () => json(201, dispatch({})),
    });
    const list = await screen.findByRole("list", { name: "Joʻnatiladigan SKUʼlar" });
    expect(within(list).getByText("taxminiy tannarx")).toBeTruthy();
    expect(within(list).getByText("tannarx nomaʼlum")).toBeTruthy();
    expect(norm(within(list).getAllByRole("listitem")[0]!.textContent!)).toContain(`~${norm(f.money("10000.00"))}`);
    const save = screen.getByRole("button", { name: /^Excel yuklab olish/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Tannarx: Koʻylak-Oq"), { target: { value: "12000" } });
    fireEvent.change(screen.getByLabelText("Tannarx: Mashina-Qizil"), { target: { value: "11000" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, CREATE_ROUTE)[0]).toEqual({
      shop_id: SHOPS[0]!.id,
      items: [
        { sku_id: SKU_A, qty: 70, unit_cost: "11000" },
        { sku_id: SKU_B, qty: 5, unit_cost: "12000" },
      ],
    });
  });

  it("ro'yxat: holatlar, nomzod postavkani tanlash, bog'lanishni olib tashlash, bekor qilish", async () => {
    const link1 = `POST /api/v1/orgs/${ORG}/dispatches/${D1}/link`;
    const link2 = `POST /api/v1/orgs/${ORG}/dispatches/${D2}/link`;
    const cancel = `POST /api/v1/orgs/${ORG}/dispatches/${D1}/cancel`;
    const api = await renderAt({ [link1]: () => json(200, dispatch({})), [link2]: () => json(200, dispatch({})), [cancel]: () => json(200, dispatch({ status: "canceled" })) });
    const list = await screen.findByRole("list", { name: "Joʻnatmalar" });
    expect(within(list).getByText("Joʻnatilmoqda")).toBeTruthy();
    expect(within(list).getByText("Uzumda · postavka № 109")).toBeTruthy();
    expect(within(list).getByText("Bekor qilingan")).toBeTruthy();
    fireEvent.change(within(list).getByLabelText("Postavka"), { target: { value: "i2" } });
    await waitFor(() => expect(bodiesOf(api, link1)).toEqual([{ invoice_id: "i2" }]));
    fireEvent.click(within(list).getByRole("button", { name: "Bogʻlanishni olib tashlash" }));
    await waitFor(() => expect(bodiesOf(api, link2)).toEqual([{ invoice_id: null }]));
    fireEvent.click(within(list).getByRole("button", { name: /^Bekor qilish/ }));
    await waitFor(() => expect(api.count(cancel)).toBe(1));
    expect(await screen.findByText(/Joʻnatma bekor qilindi/)).toBeTruthy();
  });

  it("TM9.1: qisman mos nomzod (SKU ulushi), boshqa postavka — hammasidan, tenglashtirish izohi", async () => {
    const link1 = `POST /api/v1/orgs/${ORG}/dispatches/${D1}/link`;
    const all = `GET /api/v1/orgs/${ORG}/dispatches/${D1}/invoices`;
    const api = await renderAt({
      [LIST_ROUTE]: () =>
        json(200, {
          items: [
            dispatch({ id: D1, candidates: [{ ...inv("i1", 101), common: 1, union: 2 }] }),
            dispatch({ id: D2, status: "linked", invoice: inv("i9", 109), adjustments: [{ sku_id: SKU_A, title: "Mashina-Qizil", before: 20, after: 18, declared: 18 }] }),
          ],
        }),
      [all]: () => json(200, [inv("i7", 107)]),
      [link1]: () => json(200, dispatch({})),
    });
    const list = await screen.findByRole("list", { name: "Joʻnatmalar" });
    expect(within(list).getByRole("option", { name: /№ 101 · .* · 1\/2 SKU mos/ })).toBeTruthy();
    expect(list.textContent).toContain("Postavkada eʼlon qilingan songa tenglashtirildi: Mashina-Qizil 20 → 18 (eʼlon 18)");
    fireEvent.click(within(list).getByRole("button", { name: "Boshqa postavka tanlash" }));
    await within(list).findByRole("option", { name: /№ 107/ });
    fireEvent.change(within(list).getByLabelText("Boshqa postavka tanlash"), { target: { value: "i7" } });
    await waitFor(() => expect(bodiesOf(api, link1)).toEqual([{ invoice_id: "i7" }]));
  });

  it("TM9.1: dasturdan tashqari postavka — «Omborimdan ketgan» / «Omborimdan emas»", async () => {
    const sent = `POST /api/v1/orgs/${ORG}/dispatches/orphans/i5/sent`;
    const notMine = `POST /api/v1/orgs/${ORG}/dispatches/orphans/i6/not-mine`;
    const orphan = (id: string, number: number, accepted: string | null) => ({ invoice: inv(id, number), shop: "byDurii", accepted_on: accepted, items: [{ sku_id: SKU_A, title: "Mashina-Qizil", declared: 5, available: 8 }] });
    const api = await renderAt({
      [ORPHANS_ROUTE]: () => json(200, { items: [orphan("i5", 105, "2026-11-12"), orphan("i6", 106, null)] }),
      [sent]: () => json(201, dispatch({ status: "linked", origin: "invoice" })),
      [notMine]: () => new Response(null, { status: 204 }),
    });
    const section = await screen.findByRole("list", { name: "Dasturdan tashqari postavkalar: 2 ta" });
    expect(section.textContent).toContain("Mashina-Qizil: postavkada 5, Omborimda 8");
    expect(within(section).getByText(/Qabul qilingan/)).toBeTruthy();
    fireEvent.click(within(section).getByRole("button", { name: "Omborimdan ketgan: № 105" }));
    await waitFor(() => expect(api.count(sent)).toBe(1));
    fireEvent.click(within(section).getByRole("button", { name: "Omborimdan emas: № 106" }));
    await waitFor(() => expect(api.count(notMine)).toBe(1));
  });

  it("buxgalter: faqat ro'yxat (amallarsiz); bo'sh holatlar", async () => {
    await renderAt({}, "accountant");
    await screen.findByRole("list", { name: "Joʻnatmalar" });
    expect(screen.queryByRole("heading", { name: "Yangi joʻnatma" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Bekor qilish/ })).toBeNull();
    cleanup();
    await renderAt({ [LIST_ROUTE]: () => json(200, { items: [] }), [DRAFT_ROUTE]: () => json(200, { shop_id: SHOP, rows: [], no_barcode: [] }) });
    expect(await screen.findByText("Joʻnatmalar yoʻq")).toBeTruthy();
    expect(await screen.findByText("Bu doʻkon uchun Omborimda tovar yoʻq")).toBeTruthy();
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt();
    await screen.findByRole("list", { name: "Joʻnatmalar" });
    await screen.findByRole("list", { name: "Joʻnatiladigan SKUʼlar" });
    const results = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});

