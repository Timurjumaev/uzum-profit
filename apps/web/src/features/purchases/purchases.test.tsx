// Xaridlar (M9, B4.6): ro'yxat (bosqich guruhi URL'da, ixcham Partiya yo'li, taxminiy "~"), yangi xarid (yetkazib
// beruvchi nomi bilan), xarid sahifasi (Partiya yo'li, qatorlar, komponentlar va kurs, tannarx tarkibi, bannerlar),
// tahrirlar tanasi, omborchi — summasiz. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { todayTashkent } from "../../lib/dates";
import { formatterFor } from "../../lib/format";
import {
  CARRIERS_ROUTE,
  ITEMS_ROUTE,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  PURCHASE_CREATE_ROUTE,
  purchaseRoute,
  PURCHASES_ROUTE,
  purchaseSubRoute,
  SUPPLIER_CREATE_ROUTE,
  SUPPLIERS_ROUTE,
  type Routes,
} from "../../test/api";
import { component, COMP_GOODS, line, LINE_1, PURCHASE_1, PURCHASE_2, purchaseDetail, purchaseRow, timeline } from "../../test/purchases";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));
const DETAIL = `/purchases/${PURCHASE_1}`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [PURCHASES_ROUTE]: () => json(200, { items: [purchaseRow(), purchaseRow({ id: PURCHASE_2, title: null, stage: "draft", timeline: timeline("ordered", {}).map((m) => ({ ...m, state: "upcoming", days: null })), items: [], line_count: 0, units_ordered: 0, total: null, unit_cost: null, flags: [] })], amounts: true }),
    [purchaseRoute("GET", PURCHASE_1)]: () => json(200, purchaseDetail()),
    [SUPPLIERS_ROUTE]: () => json(200, [{ id: "s1", name: "Yiwu Toys", platform: "1688" }]),
    [CARRIERS_ROUTE]: () => json(200, []),
    [ITEMS_ROUTE]: () => json(200, { items: [{ id: "e1111111-1111-4111-8111-111111111111", name: "Mashina", image_url: null, sku_count: 1 }] }),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("xaridlar ro'yxati", () => {
  it("ixcham Partiya yo'li, dona, jami va taxminiy tannarx; nomsiz qoralama", async () => {
    await renderAt("/purchases");
    const table = await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    const rows = within(table).getAllByRole("row");
    const first = norm(rows[1]!.textContent!);
    expect(first).toContain("Oktabr partiyasi");
    expect(first).toContain("Mashina, Yangi oʻyinchoq");
    expect(first).toContain("Yoʻlda · 11 kun · kutilmoqda ~28.10");
    expect(first).toContain("150 buyurtma");
    expect(first).toContain(n("4664000.00"));
    expect(first).toContain(`~${n("31093.33")}`); // kargo kiritilmagan — taxminiy
    expect(norm(rows[2]!.textContent!)).toContain("Nomsiz xarid");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Xaridlar");
  });

  it("bosqich guruhi URL'da va API'ga `stage` bo'lib boradi", async () => {
    const { api, history } = await renderAt("/purchases");
    await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    fireEvent.click(screen.getByRole("tab", { name: "Yoʻlda" }));
    await waitFor(() => expect(history.location.search).toContain("group=transit"));
    await waitFor(() => {
      const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url));
      expect(urls.some((u) => u.pathname.endsWith("/purchases") && u.searchParams.getAll("stage").join() === "cn_warehouse,shipped,arrived")).toBe(true);
    });
  });

  it("bo'sh — taklif; yangi xarid: yangi yetkazib beruvchi nomi bilan yaratiladi va xarid sahifasiga o'tiladi", async () => {
    const { api, history } = await renderAt("/purchases", {
      [PURCHASES_ROUTE]: () => json(200, { items: [], amounts: true }),
      [SUPPLIER_CREATE_ROUTE]: () => json(201, { id: "s2", name: "Guangzhou", platform: null }),
      [PURCHASE_CREATE_ROUTE]: () => json(201, purchaseDetail()),
    });
    expect(await screen.findByText("Xaridlar yoʻq")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Yangi xarid" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarid (partiya)" });
    fireEvent.change(within(dialog).getByLabelText(/^Nomi/), { target: { value: " Noyabr " } });
    await within(dialog).findByRole("option", { name: "Yiwu Toys" });
    fireEvent.change(within(dialog).getByLabelText("Yetkazib beruvchi"), { target: { value: "__new" } });
    const save = within(dialog).getByRole("button", { name: "Xaridni saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // yangi nom kiritilmagan
    fireEvent.change(within(dialog).getByLabelText("Yetkazib beruvchi nomi"), { target: { value: "Guangzhou" } });
    fireEvent.change(within(dialog).getByLabelText(/^Buyurtma sanasi/), { target: { value: "2026-10-25" } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, PURCHASE_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, SUPPLIER_CREATE_ROUTE)[0]).toEqual({ name: "Guangzhou" });
    expect(bodiesOf(api, PURCHASE_CREATE_ROUTE)[0]).toEqual({ title: "Noyabr", supplier_id: "s2", carrier_id: null, note: null, dates: { ordered: "2026-10-25" } });
    await waitFor(() => expect(history.location.pathname).toBe(DETAIL));
  });

  it("buxgalter yangi xarid qo'sha olmaydi; omborchi — summalarsiz", async () => {
    await renderAt("/purchases", {}, "accountant");
    await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    expect(screen.queryByRole("button", { name: "Yangi xarid" })).toBeNull();
    cleanup();
    await renderAt("/purchases", { [PURCHASES_ROUTE]: () => json(200, { items: [purchaseRow({ total: null, unit_cost: null })], amounts: false }) }, "warehouse");
    const table = await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    expect(within(table).queryByRole("columnheader", { name: "Jami" })).toBeNull();
    expect(screen.getByText("Summalar sizga koʻrinmaydi")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Yangi xarid" })).toBeTruthy();
  });
});

describe("xarid sahifasi", () => {
  it("Partiya yo'li, qatorlar (kamomad, qabul qilinmagan, havola), komponent kursi, tannarx tarkibi", async () => {
    await renderAt(DETAIL);
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Oktabr partiyasi");
    const path = screen.getByRole("list", { name: "Partiya yoʻli" });
    expect(within(path).getAllByRole("listitem")).toHaveLength(8);
    expect(norm(path.textContent!)).toContain("kutilmoqda ~28.10");
    const lines = screen.getByRole("table", { name: "Qatorlar" });
    expect(within(lines).getByText("kamomad 2")).toBeTruthy();
    expect(within(lines).getByText("qabul qilinmagan")).toBeTruthy();
    expect(within(lines).getByRole("link", { name: /Havola/ }).getAttribute("href")).toBe("https://detail.1688.com/offer/1.html");
    const comps = screen.getByRole("table", { name: "Xarajat komponentlari" });
    expect(norm(comps.textContent!)).toContain(`1 800 (Markaziy bank, ${f.date("2026-10-03")})`);
    expect(norm(comps.textContent!)).toContain(n("2664000.00"));
    const cost = screen.getByRole("complementary", { name: /Birlik tannarx tarkibi/ });
    expect(norm(cost.textContent!)).toContain(norm(f.money("4664000.00")));
    expect(norm(cost.textContent!)).toContain(`~${norm(f.money("31093.33"))}`);
    expect(within(cost).getByText("kargo kiritilmagan")).toBeTruthy();
  });

  it("keyingi bosqich — bugungi sana bilan PATCH; javob keshga qo'yiladi", async () => {
    const arrived = purchaseDetail({ purchase: purchaseRow({ stage: "arrived", timeline: timeline("arrived", { arrived: todayTashkent() }) }) });
    const { api } = await renderAt(DETAIL, { [purchaseRoute("PATCH", PURCHASE_1)]: () => json(200, arrived) });
    fireEvent.click(await screen.findByRole("button", { name: "«Toshkentga keldi» — bugun" }));
    await waitFor(() => expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))).toHaveLength(1));
    expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))[0]).toEqual({ dates: { arrived: todayTashkent() } });
    expect(await screen.findByRole("button", { name: "«Qabul qilindi» — bugun" })).toBeTruthy();
  });

  it("bosqich sanalari: tartib buzilsa saqlab bo'lmaydi; faqat o'zgargan sanalar yuboriladi", async () => {
    const { api } = await renderAt(DETAIL, { [purchaseRoute("PATCH", PURCHASE_1)]: () => json(200, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Bosqich sanalari" }));
    const dialog = await screen.findByRole("dialog", { name: "Bosqich sanalari" });
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-01" } });
    const save = within(dialog).getByRole("button", { name: "Xaridni saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(within(dialog).getByText(/Sanalar tartibi buzilgan/)).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-27" } });
    fireEvent.change(within(dialog).getByLabelText(/^Toʻlandi/), { target: { value: "" } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))).toHaveLength(1));
    expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))[0]).toEqual({ dates: { paid: null, arrived: "2026-10-27" } });
  });

  it("qator qo'shish: yangi tovar (havola, variant), qabul bo'sh — null", async () => {
    const route = purchaseSubRoute("POST", PURCHASE_1, "lines");
    const { api } = await renderAt(DETAIL, { [route]: () => json(201, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Qator qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi qator" });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Yangi tovar" }));
    fireEvent.change(within(dialog).getByLabelText("Tovar nomi (vaqtincha)"), { target: { value: "Ayiqcha" } });
    fireEvent.change(within(dialog).getByLabelText(/^Tovar sahifasi/), { target: { value: "https://detail.1688.com/offer/2.html" } });
    fireEvent.change(within(dialog).getByLabelText(/^Variant/), { target: { value: "koʻk" } });
    fireEvent.change(within(dialog).getByLabelText("Buyurtma qilingan dona"), { target: { value: "40" } });
    fireEvent.change(within(dialog).getByLabelText(/^Dona narxi/), { target: { value: "12,5" } });
    fireEvent.change(within(dialog).getByLabelText(/^Dona vazni/), { target: { value: "0,3" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, route)).toHaveLength(1));
    expect(bodiesOf(api, route)[0]).toEqual({
      item_id: null,
      temp_name: "Ayiqcha",
      url: "https://detail.1688.com/offer/2.html",
      image_url: null,
      variant: "koʻk",
      ordered_qty: 40,
      received_qty: null,
      unit_weight: "0.3",
      unit_volume: null,
      unit_price: "12.5",
      currency: "CNY",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("xarajat: kartadan yechilgan summa (effektiv kurs), tanlangan qatorlar; tahrirlash va o'chirish", async () => {
    const post = purchaseSubRoute("POST", PURCHASE_1, "components");
    const patch = purchaseSubRoute("PATCH", PURCHASE_1, `components/${COMP_GOODS}`);
    const del = purchaseSubRoute("DELETE", PURCHASE_1, `components/${COMP_GOODS}`);
    const { api } = await renderAt(DETAIL, {
      [post]: () => json(201, purchaseDetail()),
      [patch]: () => json(200, purchaseDetail({ components: [component({ rate_mode: "manual", rate: "1810.000000", applied_rate: "1810.000000" })] })),
      [del]: () => json(200, purchaseDetail({ components: [] })),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "goods" } });
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "1000" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Kartadan yechilgan summadan" }));
    fireEvent.change(within(dialog).getByLabelText(/^Kartadan yechilgan summa\s*$/), { target: { value: "142,50" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Hamma qatorlar" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Yangi oʻyinchoq/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, post)).toHaveLength(1));
    expect(bodiesOf(api, post)[0]).toEqual({
      kind: "goods",
      amount: "1000",
      currency: "CNY",
      paid_on: null,
      rate_mode: "effective",
      rate: null,
      charged_amount: "142.50",
      charged_currency: "USD",
      allocation: null,
      lines: [LINE_1],
      shares: {},
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const comps = screen.getByRole("table", { name: "Xarajat komponentlari" });
    fireEvent.click(within(comps).getByRole("button", { name: "Tahrirlash: Tovar" }));
    const edit = await screen.findByRole("dialog", { name: "Xarajatni tahrirlash" });
    fireEvent.click(within(edit).getByRole("radio", { name: "Qoʻlda kurs" }));
    fireEvent.change(within(edit).getByLabelText(/^1 birlik/), { target: { value: "1810" } });
    fireEvent.click(within(edit).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, patch)).toHaveLength(1));
    expect(bodiesOf(api, patch)[0]).toMatchObject({ rate_mode: "manual", rate: "1810", allocation: "value", lines: null });
    expect(await screen.findByText(/1 810 \(qoʻlda/)).toBeTruthy();
    fireEvent.click(within(screen.getByRole("table", { name: "Xarajat komponentlari" })).getByRole("button", { name: "Oʻchirish: Tovar" }));
    expect(await screen.findByText("Xarajatlar kiritilmagan")).toBeTruthy();
  });

  it("hisoblab bo'lmasa — sabab, summasiz; qayta hisob banneri; server xatosi toast'da", async () => {
    await renderAt(DETAIL, {
      [purchaseRoute("GET", PURCHASE_1)]: () =>
        json(200, purchaseDetail({ purchase: purchaseRow({ error: "customs: qoʻlda ulush berilmagan", total: null, unit_cost: null }), recalc_pending: true, by_kind: {} })),
      [purchaseSubRoute("DELETE", PURCHASE_1, `lines/${LINE_1}`)]: () => problem(409, "line_in_use"),
    });
    expect(await screen.findByText(/Tannarxni hisoblab boʻlmadi: customs/)).toBeTruthy();
    expect(screen.getByText("Sotuvlar tannarxi qayta hisoblanmoqda")).toBeTruthy();
    fireEvent.click(within(screen.getByRole("table", { name: "Qatorlar" })).getByRole("button", { name: "Oʻchirish: Mashina" }));
    expect(await screen.findByText(/Bu qator xarajatda alohida tanlangan/)).toBeTruthy();
  });

  it("omborchi: summasiz (narx, komponentlar, tannarx yo'q), qabul donasini kiritadi — narx yuborilmaydi", async () => {
    const hidden = purchaseDetail({
      amounts: false,
      components: [],
      by_kind: {},
      purchase: purchaseRow({ total: null, unit_cost: null }),
      lines: [line({ unit_price: null, cost: null })],
    });
    const route = purchaseSubRoute("PATCH", PURCHASE_1, `lines/${LINE_1}`);
    const { api } = await renderAt(DETAIL, { [purchaseRoute("GET", PURCHASE_1)]: () => json(200, hidden), [route]: () => json(200, hidden) }, "warehouse");
    const lines = await screen.findByRole("table", { name: "Qatorlar" });
    expect(within(lines).queryByRole("columnheader", { name: "Narx" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Xarajat komponentlari" })).toBeNull();
    expect(screen.getByText("Summalar koʻrinmaydi.")).toBeTruthy();
    fireEvent.click(within(lines).getByRole("button", { name: "Tahrirlash: Mashina" }));
    const dialog = await screen.findByRole("dialog", { name: "Qatorni tahrirlash" });
    expect(within(dialog).queryByLabelText(/^Dona narxi/)).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(/^Qabul qilingan dona/), { target: { value: "100" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, route)).toHaveLength(1));
    expect(bodiesOf(api, route)[0]).toMatchObject({ received_qty: 100, item_id: "e1111111-1111-4111-8111-111111111111" });
    expect(bodiesOf(api, route)[0]).not.toHaveProperty("unit_price");
  });

  it("qayta buyurtma — yangi qoralamaga o'tadi; o'chirish — tasdiq va ro'yxatga qaytish", async () => {
    const copy = purchaseSubRoute("POST", PURCHASE_1, "copy");
    const { api, history } = await renderAt(DETAIL, {
      [copy]: () => json(201, purchaseDetail({ purchase: purchaseRow({ id: PURCHASE_2, stage: "draft" }) })),
      [purchaseRoute("GET", PURCHASE_2)]: () => json(200, purchaseDetail({ purchase: purchaseRow({ id: PURCHASE_2, stage: "draft" }) })),
      [purchaseRoute("DELETE", PURCHASE_2)]: () => new Response(null, { status: 204 }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Qayta buyurtma" }));
    await waitFor(() => expect(history.location.pathname).toBe(`/purchases/${PURCHASE_2}`));
    fireEvent.click(await screen.findByRole("button", { name: "Oʻchirish" }));
    const dialog = await screen.findByRole("dialog", { name: "Xaridni oʻchirish" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.count(purchaseRoute("DELETE", PURCHASE_2))).toBe(1));
    await waitFor(() => expect(history.location.pathname).toBe("/purchases"));
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt(DETAIL);
    await screen.findByRole("table", { name: "Qatorlar" });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
