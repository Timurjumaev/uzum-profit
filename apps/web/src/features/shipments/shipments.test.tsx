// Kargolar (M9, B4.31, ADR-046): ro'yxat, kargo sahifasi (xaridlar, kargo ulushi, xarajatlar, tovarlar), xarajat qo'shish,
// o'chirish (xaridli kargo — bloklangan), omborchi — summasiz; xarid sahifasida kargo bloki va sanalar kargodan.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import {
  json,
  ME,
  ME_ROUTE,
  mockApi,
  purchaseRoute,
  shipmentRoute,
  shipmentSubRoute,
  SHIPMENTS_ROUTE,
  SKU_PICKER_ROUTE,
  SUPPLIERS_ROUTE,
  CARRIERS_ROUTE,
  problem,
  type Routes,
} from "../../test/api";
import { PURCHASE_1, purchaseDetail, purchaseRow, component, timeline } from "../../test/purchases";
import { shipmentDetail, shipmentRow, SHIPMENT_1, SHIPMENT_COMP } from "../../test/shipments";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [SHIPMENTS_ROUTE]: () => json(200, { items: [shipmentRow(), shipmentRow({ id: "b2222222-2222-4222-8222-222222222222", title: null, carrier_name: null, purchase_count: 0, units: 0, total: "0.00", shipped_on: null, cn_warehouse_on: null })], amounts: true }),
    [shipmentRoute(SHIPMENT_1)]: () => json(200, shipmentDetail()),
    [purchaseRoute("GET", PURCHASE_1)]: () => json(200, purchaseDetail()),
    [SKU_PICKER_ROUTE]: () => json(200, { rows: [], truncated: false }),
    [SUPPLIERS_ROUTE]: () => json(200, []),
    [CARRIERS_ROUTE]: () => json(200, [{ id: "c1", name: "Cargo Express", pricing: null }]),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("kargolar ro'yxati", () => {
  it("sanalar, xaridlar soni, dona va kargo xarajati jami; nomsiz kargo", async () => {
    await renderAt("/shipments");
    const table = await screen.findByRole("table", { name: "Kargolar" });
    const rows = within(table).getAllByRole("row");
    const first = norm(rows[1]!.textContent!);
    expect(first).toContain("Presslangan oʻram");
    expect(first).toContain("Cargo Express");
    expect(first).toContain(n("2430000.00"));
    expect(first).toContain("340");
    expect(norm(rows[2]!.textContent!)).toContain("Nomsiz kargo");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Kargolar");
  });

  it("omborchi summalarni ko'rmaydi; bo'sh holat taklif bilan", async () => {
    await renderAt("/shipments", { [SHIPMENTS_ROUTE]: () => json(200, { items: [shipmentRow({ total: null })], amounts: false }) }, "warehouse");
    const table = await screen.findByRole("table", { name: "Kargolar" });
    expect(within(table).queryByRole("columnheader", { name: "Kargo xarajati" })).toBeNull();
    cleanup();
    await renderAt("/shipments", { [SHIPMENTS_ROUTE]: () => json(200, { items: [], amounts: true }) });
    expect(await screen.findByText("Kargolar yoʻq")).toBeTruthy();
  });

  it("yangi kargo: nomi, sanalar tartibi tekshiriladi, saqlangach kargo sahifasiga o'tiladi", async () => {
    const create = shipmentSubRoute("POST", "");
    const { api, history } = await renderAt("/shipments", { [create]: () => json(201, shipmentDetail()) });
    fireEvent.click((await screen.findAllByRole("button", { name: "Yangi kargo" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Yangi kargo" });
    fireEvent.change(within(dialog).getByLabelText(/^Nomi/), { target: { value: "Noyabr" } });
    fireEvent.change(within(dialog).getByLabelText(/^Yoʻlda/), { target: { value: "2026-10-12" } });
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-10" } });
    expect((within(dialog).getByRole("button", { name: "Xaridni saqlash" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-25" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, create)).toHaveLength(1));
    expect(bodiesOf(api, create)[0]).toEqual({ title: "Noyabr", carrier_id: null, cn_warehouse_on: null, shipped_on: "2026-10-12", arrived_on: "2026-10-25", note: null });
    await waitFor(() => expect(history.location.pathname).toBe(`/shipments/${SHIPMENT_1}`));
  });
});

describe("kargo sahifasi", () => {
  it("xaridlar (kargo ulushi), xarajatlar, tovarlar va jami; belgilar tushuntiriladi", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`);
    const purchases = await screen.findByRole("table", { name: "Kargodagi xaridlar" });
    const first = norm(within(purchases).getAllByRole("row")[1]!.textContent!);
    expect(first).toContain("A yetkazib beruvchi");
    expect(first).toContain(n("1682307.69")); // kargo ulushi
    expect(first).toContain(n("1782307.69")); // jami = o'z xarajatlari + ulush
    const costs = screen.getByRole("table", { name: "Kargo xarajatlari" });
    expect(within(costs).getByText("Kargo")).toBeTruthy();
    expect(norm(costs.textContent!)).toContain(n("2430000.00"));
    const lines = screen.getByRole("table", { name: "Tovarlar va kargo ulushi" });
    expect(norm(lines.textContent!)).toContain(n("934615.38"));
    expect(norm(lines.textContent!)).toContain(n("9346.15"));
    expect(screen.getByText(/vazn yoʻq|dona boʻyicha taqsimlangan/)).toBeTruthy(); // base_fallback belgisi
    expect(screen.getByText(/Xitoy omborida 09\./)).toBeTruthy();
  });

  it("xarajat qo'shish: tovarlar hamma xaridlardan, kargo API'siga ketadi", async () => {
    const post = shipmentSubRoute("POST", SHIPMENT_1, "components");
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, { [post]: () => json(201, shipmentDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    fireEvent.change(within(dialog).getByLabelText("Summa"), { target: { value: "300" } });
    fireEvent.change(within(dialog).getByLabelText("Valyuta"), { target: { value: "USD" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Hamma tovarlar" }));
    // Nishonlar: har xarid nomi bilan.
    expect(within(dialog).getByRole("checkbox", { name: /A yetkazib beruvchi · Mashina/ })).toBeTruthy();
    expect(within(dialog).getByRole("checkbox", { name: /B yetkazib beruvchi · Mashina/ })).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /B yetkazib beruvchi · Mashina/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, post)).toHaveLength(1));
    expect(bodiesOf(api, post)[0]).toMatchObject({ amount: "300", currency: "USD", lines: expect.arrayContaining([expect.any(String)]) });
  });

  it("xarajatni o'chirish; hisoblab bo'lmasa — sabab, raqam yo'q", async () => {
    const del = shipmentSubRoute("DELETE", SHIPMENT_1, `components/${SHIPMENT_COMP}`);
    const broken = shipmentDetail({ error: "kargo hisoblanmadi: USD uchun kurs yo'q", purchases: shipmentDetail().purchases.map((p) => ({ ...p, share: null, total: null, unit_cost: null, error: "kargo hisoblanmadi" })) });
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => json(200, broken), [del]: () => json(200, shipmentDetail({ components: [], by_kind: {} })) });
    expect(await screen.findByText(/Kargoni hisoblab boʻlmadi/)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Oʻchirish: Kargo" }));
    await waitFor(() => expect(api.count(del)).toBe(1));
  });

  it("kargoni o'chirish: xaridli — bloklangan; xaridsiz — o'chadi va ro'yxatga qaytadi", async () => {
    const del = shipmentSubRoute("DELETE", SHIPMENT_1);
    const empty = shipmentDetail({ shipment: shipmentRow({ purchase_count: 0 }), purchases: [], lines: [], components: [], by_kind: {} });
    const first = await renderAt(`/shipments/${SHIPMENT_1}`, { [del]: () => new Response(null, { status: 204 }) });
    fireEvent.click(await screen.findByRole("button", { name: "Oʻchirish" }));
    let dialog = await screen.findByRole("dialog", { name: "Kargoni oʻchirish" });
    expect(within(dialog).getByText(/Kargoda xaridlar bor/)).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "Oʻchirish" }) as HTMLButtonElement).disabled).toBe(true);
    expect(first.api.count(del)).toBe(0); // xaridli kargo o'chirilmaydi
    cleanup();
    const { api, history } = await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => json(200, empty), [del]: () => new Response(null, { status: 204 }) });
    fireEvent.click(await screen.findByRole("button", { name: "Oʻchirish" }));
    dialog = await screen.findByRole("dialog", { name: "Kargoni oʻchirish" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(history.location.pathname).toBe("/shipments"));
    expect(api.count(del)).toBe(1);
  });

  it("omborchi: xaridlar va tovarlar bor, summa va xarajatlar yo'q; a11y", async () => {
    const hidden = shipmentDetail({
      amounts: false,
      components: [],
      by_kind: {},
      shipment: shipmentRow({ total: null }),
      purchases: shipmentDetail().purchases.map((p) => ({ ...p, share: null, total: null, unit_cost: null })),
      lines: shipmentDetail().lines.map((l) => ({ ...l, share: null, share_per_unit: null })),
    });
    await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => json(200, hidden) }, "warehouse");
    await screen.findByRole("table", { name: "Kargodagi xaridlar" });
    expect(screen.queryByRole("table", { name: "Kargo xarajatlari" })).toBeNull();
    expect(screen.getByText("Summalar sizga koʻrinmaydi")).toBeTruthy();
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });

  it("xato (kargo topilmadi) — banner va qayta urinish", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => problem(404, "shipment_not_found") });
    expect(await screen.findByText(/Kargo topilmadi/)).toBeTruthy();
  });
});

describe("xarid sahifasida kargo", () => {
  const linked = () =>
    purchaseDetail({
      purchase: purchaseRow({ shipment_id: SHIPMENT_1, shipment_name: "Presslangan oʻram", timeline: timeline("shipped", { ordered: "2026-10-02", shipped: "2026-10-12" }) }),
      shipment_components: [component({ id: SHIPMENT_COMP, kind: "cargo", amount: "2430000.0000", currency: "UZS", applied_rate: null, rate_day: null, rate_source: null, amount_uzs: "2430000.00" })],
    });

  it("kargo havolasi, kargodan xarajatlar (faqat o'qish), sanalar kargodan: «keyingi bosqich» tugmasi va sana maydonlari bloklangan", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, { [purchaseRoute("GET", PURCHASE_1)]: () => json(200, linked()), [patch]: () => json(200, linked()) });
    expect((await screen.findAllByRole("link", { name: /Kargo: Presslangan oʻram/ }))[0]!.getAttribute("href")).toBe(`/shipments/${SHIPMENT_1}`);
    const shared = screen.getByRole("table", { name: "Kargodan xarajatlar" });
    expect(norm(shared.textContent!)).toContain(n("2430000.00"));
    expect(within(shared).queryByRole("button", { name: /Tahrirlash/ })).toBeNull();
    // Keyingi bosqich "Toshkentga keldi" kargo sanasi: tugma yo'q.
    expect(screen.queryByRole("button", { name: /Toshkentga keldi.*bugun/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Bosqich sanalari" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bosqich sanalari" }));
    const dialog = await screen.findByRole("dialog", { name: "Bosqich sanalari" });
    expect((within(dialog).getByLabelText(/^Yoʻlda/) as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog).getByLabelText(/^Buyurtma berildi/) as HTMLInputElement).disabled).toBe(false);
    fireEvent.change(within(dialog).getByLabelText(/^Buyurtma berildi/), { target: { value: "2026-10-01" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).toEqual({ dates: { ordered: "2026-10-01" } }); // kargo sanalari yuborilmaydi
  });

  it("xarid shakli: kargo tanlanadi va faqat o'zgarganda yuboriladi", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, { [patch]: () => json(200, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Tahrirlash" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Nomi/), { target: { value: "Yangi nom" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).not.toHaveProperty("shipment_id"); // kargo o'zgarmadi
  });
});
