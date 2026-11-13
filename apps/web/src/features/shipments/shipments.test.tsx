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
  PURCHASES_ROUTE,
  purchaseRoute,
  purchaseSubRoute,
  shipmentRoute,
  shipmentSubRoute,
  SHIPMENTS_ROUTE,
  SKU_PICKER_ROUTE,
  SUPPLIERS_ROUTE,
  CARRIERS_ROUTE,
  problem,
  type Routes,
} from "../../test/api";
import { PURCHASE_1, PURCHASE_2, purchaseDetail, purchaseRow, component, timeline } from "../../test/purchases";
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
    expect((within(dialog).getByRole("button", { name: "Kargoni saqlash" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-25" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Kargoni saqlash" }));
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
    fireEvent.click(within(dialog).getByRole("button", { name: "Xarajatni saqlash" }));
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

  it("kargo havolasi, kargodan xarajatlar (faqat o'qish), sanalar kargodan: kargo sana maydonlari bloklangan", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, { [purchaseRoute("GET", PURCHASE_1)]: () => json(200, linked()), [patch]: () => json(200, linked()) });
    expect((await screen.findAllByRole("link", { name: /Kargo: Presslangan oʻram/ }))[0]!.getAttribute("href")).toBe(`/shipments/${SHIPMENT_1}`);
    const shared = screen.getByRole("table", { name: "Kargodan xarajatlar" });
    expect(norm(shared.textContent!)).toContain(n("2430000.00"));
    expect(within(shared).queryByRole("button", { name: /Tahrirlash/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sanalar" }));
    const dialog = await screen.findByRole("dialog", { name: "Xarid sanalari" });
    expect((within(dialog).getByLabelText(/^Yoʻlda/) as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog).getByLabelText(/^Buyurtma berildi/) as HTMLInputElement).disabled).toBe(false);
    fireEvent.change(within(dialog).getByLabelText(/^Buyurtma berildi/), { target: { value: "2026-10-01" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Sanalarni saqlash" }));
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

describe("xaridni kargoga biriktirish — xarid sahifasidan (Turi = Kargo)", () => {
  const SHIPMENT_2 = "b2222222-2222-4222-8222-222222222222";
  const openCargo = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "cargo" } });
    return dialog;
  };

  it("summa o'rniga kargolar ro'yxati (holati bilan); tanlansa xarid shu kargoga biriktiriladi, xarajat yaratilmaydi", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const create = purchaseSubRoute("POST", PURCHASE_1, "components");
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, { [patch]: () => json(200, purchaseDetail()), [create]: () => json(201, purchaseDetail()) });
    const dialog = await openCargo();
    expect(within(dialog).queryByLabelText("Summa")).toBeNull();
    expect(within(dialog).queryByLabelText("Valyuta")).toBeNull();
    const save = () => within(dialog).getByRole("button", { name: "Kargoga biriktirish" }) as HTMLButtonElement;
    expect(save().disabled).toBe(true); // hech narsa tanlanmagan
    const first = await within(dialog).findByRole("radio", { name: /Presslangan oʻram/ });
    expect(norm(first.closest("label")!.textContent!)).toMatch(/Cargo Express.*Yoʻlda 12\./); // holat va sana
    expect(within(dialog).getByRole("radio", { name: /Nomsiz kargo/ })).toBeTruthy();
    fireEvent.click(first);
    fireEvent.click(save());
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).toEqual({ shipment_id: SHIPMENT_1 });
    expect(api.count(create)).toBe(0);
  });

  it("«Yangi kargo…»: nomi bilan yaratiladi va xarid unga biriktiriladi; nomsiz saqlab bo'lmaydi", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const post = shipmentSubRoute("POST", "");
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, {
      [patch]: () => json(200, purchaseDetail()),
      [post]: () => json(201, shipmentDetail({ shipment: shipmentRow({ id: SHIPMENT_2, title: "Dekabr" }) })),
    });
    const dialog = await openCargo();
    fireEvent.click(await within(dialog).findByRole("radio", { name: /Yangi kargo…/ }));
    const save = () => within(dialog).getByRole("button", { name: "Kargoga biriktirish" }) as HTMLButtonElement;
    expect(save().disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Yangi kargo nomi/), { target: { value: "Dekabr" } });
    fireEvent.click(save());
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, post)[0]).toEqual({ title: "Dekabr" });
    expect(bodiesOf(api, patch)[0]).toEqual({ shipment_id: SHIPMENT_2 });
  });

  it("kargoga bog'langan xarid: hozirgi kargo belgilangan (o'zgarmasa saqlab bo'lmaydi); boshqasi — ko'chirish; «Kargosiz» — ajratish", async () => {
    const linked = purchaseDetail({ purchase: purchaseRow({ shipment_id: SHIPMENT_1, shipment_name: "Presslangan oʻram" }) });
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, { [purchaseRoute("GET", PURCHASE_1)]: () => json(200, linked), [patch]: () => json(200, purchaseDetail()) });
    const dialog = await openCargo();
    const current = (await within(dialog).findByRole("radio", { name: /Presslangan oʻram/ })) as HTMLInputElement;
    expect(current.checked).toBe(true);
    expect(norm(current.closest("label")!.textContent!)).toContain("hozirgi");
    expect((within(dialog).getByRole("button", { name: "Kargoga biriktirish" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("radio", { name: /Kargosiz/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Kargodan ajratish" }));
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).toEqual({ shipment_id: null });
  });

  it("keldi bo'lgan kargoda — sanalar kargodan olinishi haqida izoh; boshqa turlarda summa maydonlari avvalgidek", async () => {
    await renderAt(`/purchases/${PURCHASE_1}`, {
      [SHIPMENTS_ROUTE]: () => json(200, { items: [shipmentRow({ arrived_on: "2026-10-20" })], amounts: true }),
    });
    const dialog = await openCargo();
    expect(within(dialog).queryByText(/sanalari kargodan olinadi/)).toBeNull(); // belgilanmaguncha izoh yo'q
    fireEvent.click(await within(dialog).findByRole("radio", { name: /Presslangan oʻram/ }));
    expect(within(dialog).getByText(/sanalari kargodan olinadi/)).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "customs" } });
    expect(within(dialog).getByLabelText("Summa")).toBeTruthy();
    expect(within(dialog).queryByRole("radio", { name: /Presslangan oʻram/ })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Xarajatni saqlash" })).toBeTruthy();
  });

  it("kargo xarajati turlari: faqat kargoga tegishlilari, boshlang'ichi — Kargo; Tovar, Xitoy ichki yetkazish va agent xaridniki (ADR-049)", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`);
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    const kind = within(dialog).getByLabelText("Turi") as HTMLSelectElement;
    expect(kind.value).toBe("cargo");
    expect([...kind.options].map((o) => o.textContent)).toEqual(["Kargo", "Bojxona", "Qadoqlash", "Shtrix-kod / yorliq", "Uzum omboriga yetkazish", "Boshqa"]);
    // Taqsimot standarti matni kargoga mos (tovar qiymati haqida gap yo'q).
    expect(within(dialog).getByRole("option", { name: "Standart (kargo — vazn, qolgani — dona)" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Xarajatni saqlash" })).toBeTruthy();
    cleanup();
    // Xarid sahifasida esa hamma tur (Tovar boshlang'ich).
    await renderAt(`/purchases/${PURCHASE_1}`);
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const purchaseDialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    const purchaseKind = within(purchaseDialog).getByLabelText("Turi") as HTMLSelectElement;
    expect(purchaseKind.value).toBe("goods");
    expect(purchaseKind.options).toHaveLength(9);
  });

  it("kargodagi xaridni shu sahifadan ajratish: PATCH shipment_id=null; faqat o'qiy oladigan rolda tugma yo'q", async () => {
    const patch = purchaseRoute("PATCH", PURCHASE_1);
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, { [patch]: () => json(200, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Ajratish: A yetkazib beruvchi" }));
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).toEqual({ shipment_id: null });
    expect(await screen.findByText("Xarid kargodan ajratildi")).toBeTruthy();
    cleanup();
    await renderAt(`/shipments/${SHIPMENT_1}`, {}, "accountant");
    await screen.findByRole("table", { name: "Kargodagi xaridlar" });
    expect(screen.queryByRole("button", { name: /^Ajratish/ })).toBeNull();
  });

  it("kargoga avval yozilgan «Tovar» xarajati tahrirlashda turi bilan ko'rinadi; xaridsiz kargoda xarajat qo'shishdan oldin tushuntirish", async () => {
    const legacy = shipmentDetail({ components: [component({ id: SHIPMENT_COMP, kind: "goods", amount: "1000.0000", currency: "UZS", applied_rate: null, rate_day: null, rate_source: null, amount_uzs: "1000.00" })], by_kind: { goods: "1000.00" } });
    await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => json(200, legacy) });
    fireEvent.click(await screen.findByRole("button", { name: /Tahrirlash: Tovar/ }));
    const dialog = await screen.findByRole("dialog", { name: "Xarajatni tahrirlash" });
    const kind = within(dialog).getByLabelText("Turi") as HTMLSelectElement;
    expect(kind.value).toBe("goods");
    expect([...kind.options].map((o) => o.value)).toEqual(["goods", "cargo", "customs", "packaging", "labeling", "uzum_delivery", "other"]);
    cleanup();
    const empty = shipmentDetail({ shipment: shipmentRow({ purchase_count: 0, units: 0, total: "0.00" }), purchases: [], lines: [], components: [], by_kind: {} });
    await renderAt(`/shipments/${SHIPMENT_1}`, { [shipmentRoute(SHIPMENT_1)]: () => json(200, empty) });
    expect(await screen.findByText(/Avval kargoga xarid biriktiring/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Xarajat qoʻshish" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("kargo sahifasida «Kargo» turi summa bilan qoladi (kargo xarajati shu yerda kiritiladi)", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`);
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "cargo" } });
    expect(within(dialog).getByLabelText("Summa")).toBeTruthy();
    expect(within(dialog).queryByRole("radio", { name: /Yangi kargo…/ })).toBeNull();
  });
});

describe("kargoga xarid biriktirish — kargo sahifasidan", () => {
  const OTHER = "93333333-3333-4333-8333-333333333333";
  const rows = () => [
    purchaseRow({ id: PURCHASE_1, title: "A yetkazib beruvchi", shipment_id: SHIPMENT_1, shipment_name: "Presslangan oʻram" }), // allaqachon shu kargoda
    purchaseRow({ id: PURCHASE_2, title: "Kargosiz xarid", supplier_name: "Yiwu Toys", shipment_id: null, shipment_name: null, stage: "ordered" }),
    purchaseRow({ id: OTHER, title: "Boshqa kargodagi", shipment_id: "b2222222-2222-4222-8222-222222222222", shipment_name: "Dekabr" }),
  ];
  const withPurchases = (items = rows()) => ({ [PURCHASES_ROUTE]: () => json(200, { items, amounts: true }) });
  const open = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Xarid biriktirish" }));
    return screen.findByRole("dialog", { name: "Kargoga xarid biriktirish" });
  };

  it("shu kargodagi xarid ro'yxatda yo'q; kargosiz birinchi, boshqa kargodagi ko'chirilishi aytiladi; bir nechtasi biriktiriladi", async () => {
    const patch2 = purchaseRoute("PATCH", PURCHASE_2);
    const patch3 = purchaseRoute("PATCH", OTHER);
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, { ...withPurchases(), [patch2]: () => json(200, purchaseDetail()), [patch3]: () => json(200, purchaseDetail()) });
    const dialog = await open();
    const boxes = await within(dialog).findAllByRole("checkbox");
    expect(boxes).toHaveLength(2); // PURCHASE_1 allaqachon shu kargoda
    expect(norm(boxes[0]!.closest("label")!.textContent!)).toContain("Kargosiz xarid");
    expect(norm(boxes[0]!.closest("label")!.textContent!)).toContain("kargosiz");
    expect(norm(boxes[1]!.closest("label")!.textContent!)).toContain("hozir «Dekabr» kargoda — koʻchiriladi");
    const save = () => within(dialog).getByRole("button", { name: /^Biriktirish/ }) as HTMLButtonElement;
    expect(save().disabled).toBe(true);
    fireEvent.click(boxes[0]!);
    fireEvent.click(boxes[1]!);
    expect(save().textContent).toBe("Biriktirish (2)");
    fireEvent.click(save());
    await waitFor(() => expect(bodiesOf(api, patch2)).toHaveLength(1));
    await waitFor(() => expect(bodiesOf(api, patch3)).toHaveLength(1));
    expect(bodiesOf(api, patch2)[0]).toEqual({ shipment_id: SHIPMENT_1 });
    expect(bodiesOf(api, patch3)[0]).toEqual({ shipment_id: SHIPMENT_1 });
    expect(await screen.findByText("Biriktirildi: 2 ta xarid")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Kargoga xarid biriktirish" })).toBeNull());
  });

  it("biri xato bersa to'xtaydi: nechtasi biriktirilgani aytiladi, qolgani belgilangan holda qoladi", async () => {
    const patch2 = purchaseRoute("PATCH", PURCHASE_2);
    const patch3 = purchaseRoute("PATCH", OTHER);
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, {
      ...withPurchases(),
      [patch2]: () => json(200, purchaseDetail()),
      [patch3]: () => problem(422, "dates_from_shipment"),
    });
    const dialog = await open();
    const boxes = await within(dialog).findAllByRole("checkbox");
    fireEvent.click(boxes[0]!);
    fireEvent.click(boxes[1]!);
    fireEvent.click(within(dialog).getByRole("button", { name: "Biriktirish (2)" }));
    expect(await within(dialog).findByText(/1 ta xarid biriktirildi, keyingisida xato/)).toBeTruthy();
    expect(api.count(patch2)).toBe(1);
    expect(api.count(patch3)).toBe(1);
    expect(screen.getByRole("dialog", { name: "Kargoga xarid biriktirish" })).toBeTruthy(); // oyna ochiq
    expect(within(dialog).getByRole("button", { name: "Biriktirish (1)" })).toBeTruthy(); // qolgani tanlangan
  });

  it("biriktiriladigan xarid yo'q — bo'sh holat; faqat o'qiy oladigan rolda (hisobchi) tugma yo'q", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`, withPurchases([rows()[0]!]));
    const dialog = await open();
    expect(await within(dialog).findByText("Biriktiriladigan xarid yoʻq")).toBeTruthy();
    cleanup();
    await renderAt(`/shipments/${SHIPMENT_1}`, withPurchases(), "accountant");
    await screen.findByRole("table", { name: "Kargodagi xaridlar" });
    expect(screen.queryByRole("button", { name: "Xarid biriktirish" })).toBeNull();
  });

  it("a11y: biriktirish oynasi", async () => {
    await renderAt(`/shipments/${SHIPMENT_1}`, withPurchases());
    const dialog = await open();
    await within(dialog).findAllByRole("checkbox");
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
