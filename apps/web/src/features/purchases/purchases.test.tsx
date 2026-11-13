// Xaridlar (M9, B4.6): ro'yxat (bosqich guruhi URL'da, ixcham Partiya yo'li, taxminiy "~"), yangi xarid (yetkazib
// beruvchi nomi bilan), xarid sahifasi (Partiya yo'li, tovarlar, komponentlar va kurs, tannarx tarkibi, bannerlar),
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
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  PURCHASE_QUICK_ROUTE,
  purchaseRoute,
  PURCHASES_ROUTE,
  purchaseSubRoute,
  SHIPMENTS_ROUTE,
  SKU_PICKER_ROUTE,
  SUPPLIERS_ROUTE,
  type Routes,
} from "../../test/api";
import type { PickerRow } from "../../lib/api/types";
import { component, COMP_GOODS, ITEM_1, line, LINE_1, PURCHASE_1, PURCHASE_2, path as supplyPath, purchaseDetail, purchaseRow } from "../../test/purchases";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));
const DETAIL = `/purchases/${PURCHASE_1}`;
const SKU_ACTIVE = "a1111111-1111-4111-8111-111111111111";
const SKU_ARCHIVED = "a2222222-2222-4222-8222-222222222222";
const SKU_BLOCKED = "a3333333-3333-4333-8333-333333333333";
const pickerRow = (over: Partial<PickerRow>): PickerRow => ({ sku_id: null, item_id: null, item_name: null, shop_id: "b1111111-1111-4111-8111-111111111111", shop: "byDurii", product_title: null, title: null, article: null, image_url: null, stock: null, sold: null, status: null, ...over });
// Tovari bor (Mashina — partiyada ham bor), tovarsiz arxivlangan va bloklangan SKU, SKU'siz tovar.
const PICKER_ROWS: PickerRow[] = [
  pickerRow({ sku_id: SKU_ACTIVE, item_id: ITEM_1, item_name: "Mashina", product_title: "Mashina", title: "Mashina-Qizil", stock: 12, sold: 40, status: "ACTIVE" }),
  pickerRow({ sku_id: SKU_ARCHIVED, product_title: "Koʻylak", title: "Koʻylak-Oq-L", stock: 0, sold: 0, status: "ARCHIVED" }),
  pickerRow({ sku_id: SKU_BLOCKED, title: "Bloklangan sumka", stock: 0, sold: 0, status: "BLOCKED", shop: "EL-ONE" }),
  pickerRow({ item_id: "c3333333-3333-4333-8333-333333333333", item_name: "Eski tovar", shop: null, shop_id: null }),
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [PURCHASES_ROUTE]: () => json(200, { items: [purchaseRow(), purchaseRow({ id: PURCHASE_2, title: null, stage: "draft", path: supplyPath("in_transit", {}, { days: 0, expected: null }), items: [], line_count: 0, units_ordered: 0, total: null, unit_cost: null, flags: [] })], amounts: true, total: 2, page: 1, pages: 1 }),
    [purchaseRoute("GET", PURCHASE_1)]: () => json(200, purchaseDetail()),
    [SUPPLIERS_ROUTE]: () => json(200, [{ id: "s1", name: "Yiwu Toys", platform: "1688" }]),
    [CARRIERS_ROUTE]: () => json(200, []),
    [SKU_PICKER_ROUTE]: () => json(200, { rows: PICKER_ROWS, truncated: false }),
    [SHIPMENTS_ROUTE]: () => json(200, { items: [], amounts: true, total: 0, page: 1, pages: 1 }),
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

  it("holat guruhi URL'da va API'ga `state` bo'lib boradi", async () => {
    const { api, history } = await renderAt("/purchases");
    await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    fireEvent.click(screen.getByRole("tab", { name: "Omborimda" }));
    await waitFor(() => expect(history.location.search).toContain("group=in_stock"));
    await waitFor(() => {
      const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url));
      expect(urls.some((u) => u.pathname.endsWith("/purchases") && u.searchParams.getAll("state").join() === "in_stock")).toBe(true);
    });
  });

  it("sahifalash: keyingi sahifa `page` bilan, URL'da; holat guruhi 1-sahifaga qaytaradi", async () => {
    const { api, history } = await renderAt("/purchases", {
      [PURCHASES_ROUTE]: (r) => {
        const page = Number(new URL(r.url).searchParams.get("page"));
        return json(200, { items: [purchaseRow({ id: page === 2 ? PURCHASE_2 : PURCHASE_1, title: page === 2 ? "Ikkinchi sahifa" : "Birinchi sahifa" })], amounts: true, total: 120, page, pages: 3 });
      },
    });
    expect(await screen.findByText("Birinchi sahifa")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Keyingi sahifa" }));
    expect(await screen.findByText("Ikkinchi sahifa")).toBeTruthy();
    expect(history.location.search).toContain("page=2");
    const calls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname.endsWith("/purchases"));
    expect(calls.some((u) => u.searchParams.get("page") === "2" && u.searchParams.get("limit") === "50")).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "Uzumda" }));
    await waitFor(() => expect(history.location.search).not.toContain("page="));
  });

  it("bo'sh — taklif; tez xarid: tovarlar, qator summalari, jami to'landi, kurs, trek — bitta so'rov, xarid sahifasiga o'tiladi", async () => {
    const { api, history } = await renderAt("/purchases", {
      [PURCHASES_ROUTE]: () => json(200, { items: [], amounts: true }),
      [PURCHASE_QUICK_ROUTE]: () => json(201, purchaseDetail()),
    });
    expect(await screen.findByText("Xaridlar yoʻq")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Yangi xarid" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarid (partiya)" });
    const save = within(dialog).getByRole("button", { name: "Xaridni saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // tovar tanlanmagan
    const box = await within(dialog).findByRole("combobox", { name: "Tovarlar" });
    await waitFor(() => expect((box as HTMLInputElement).disabled).toBe(false));
    fireEvent.focus(box);
    fireEvent.mouseDown(within(await screen.findByRole("listbox")).getAllByRole("option").find((o) => o.textContent?.includes("Mashina"))!);
    fireEvent.change(within(dialog).getByLabelText(/^Yangi tovar/), { target: { value: " Qoʻgʻirchoq " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Qoʻshish" }));
    const qty = within(dialog).getAllByLabelText("Dona");
    expect(qty).toHaveLength(2);
    fireEvent.change(qty[0]!, { target: { value: "100" } });
    fireEvent.change(qty[1]!, { target: { value: "50" } });
    fireEvent.change(within(dialog).getByLabelText(/^Jami toʻlandi/), { target: { value: "1000" } });
    const sums = within(dialog).getAllByLabelText(/^Qator summasi/);
    fireEvent.change(sums[0]!, { target: { value: "700" } });
    fireEvent.change(sums[1]!, { target: { value: "400" } });
    expect(within(dialog).getByText("Qator summalari yigʻindisi jami toʻlangan summadan koʻp")).toBeTruthy();
    expect(save.disabled).toBe(true);
    fireEvent.change(sums[1]!, { target: { value: "250" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Oʻzim kiritaman" }));
    fireEvent.change(within(dialog).getByLabelText(/^1 CNY/), { target: { value: "1750" } });
    fireEvent.change(within(dialog).getByLabelText(/^Buyurtma sanasi/), { target: { value: "2026-10-25" } });
    fireEvent.change(within(dialog).getByLabelText(/^Trek raqami/), { target: { value: " YT123 " } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, PURCHASE_QUICK_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, PURCHASE_QUICK_ROUTE)[0]).toEqual({
      lines: [
        { sku_id: SKU_ACTIVE, qty: 100, line_sum: "700" },
        { temp_name: "Qoʻgʻirchoq", qty: 50, line_sum: "250" },
      ],
      currency: "CNY",
      rate_mode: "manual",
      paid_amount: "1000",
      rate: "1750",
      ordered_on: "2026-10-25",
      track_no: "YT123",
      note: null,
      on_hand: false,
    });
    await waitFor(() => expect(history.location.pathname).toBe(DETAIL));
  });

  it("tez xarid: bitta tovar — qator summasisiz; «Tovar qoʻlimda»; UZS — kurs soʻralmaydi", async () => {
    const { api } = await renderAt("/purchases", { [PURCHASE_QUICK_ROUTE]: () => json(201, purchaseDetail()) });
    fireEvent.click((await screen.findAllByRole("button", { name: "Yangi xarid" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarid (partiya)" });
    fireEvent.change(within(dialog).getByLabelText(/^Yangi tovar/), { target: { value: "Paket" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Qoʻshish" }));
    fireEvent.change(within(dialog).getByLabelText("Dona"), { target: { value: "20" } });
    expect(within(dialog).queryByLabelText(/^Qator summasi/)).toBeNull();
    fireEvent.click(within(dialog).getByRole("radio", { name: "UZS" }));
    expect(within(dialog).queryByRole("radio", { name: "Markaziy bank kursi" })).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(/^Jami toʻlandi/), { target: { value: "200000" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Tovar qoʻlimda/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Xaridni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, PURCHASE_QUICK_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, PURCHASE_QUICK_ROUTE)[0]).toMatchObject({ lines: [{ temp_name: "Paket", qty: 20 }], currency: "UZS", rate_mode: "cbu", paid_amount: "200000", on_hand: true, track_no: null });
    expect(bodiesOf(api, PURCHASE_QUICK_ROUTE)[0]).not.toHaveProperty("rate");
  });

  it("buxgalter yangi xarid qo'sha olmaydi; omborchi — summalarsiz", async () => {
    await renderAt("/purchases", {}, "accountant");
    await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    expect(screen.queryByRole("button", { name: "Yangi xarid" })).toBeNull();
    cleanup();
    await renderAt("/purchases", { [PURCHASES_ROUTE]: () => json(200, { items: [purchaseRow({ total: null, unit_cost: null })], amounts: false, total: 1, page: 1, pages: 1 }) }, "warehouse");
    const table = await screen.findByRole("table", { name: "Xaridlar roʻyxati" });
    expect(within(table).queryByRole("columnheader", { name: "Jami" })).toBeNull();
    expect(screen.getByText("Summalar sizga koʻrinmaydi")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Yangi xarid" })).toBeTruthy();
  });
});

describe("xarid sahifasi", () => {
  it("Partiya yo'li, tovarlar (kamomad, qabul qilinmagan, havola), komponent kursi, tannarx tarkibi", async () => {
    await renderAt(DETAIL);
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Oktabr partiyasi");
    const path = screen.getByRole("list", { name: "Partiya yoʻli" });
    expect(within(path).getAllByRole("listitem")).toHaveLength(3);
    expect(norm(path.textContent!)).toContain("Yoʻlda");
    expect(norm(path.textContent!)).toContain("Uzumda");
    expect(norm(path.textContent!)).toContain("kutilmoqda ~28.10");
    const lines = screen.getByRole("table", { name: "Partiyadagi tovarlar" });
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

  it("«Tovar keldi — bugun» — qabul sanasi PATCH; javob keshga qo'yiladi (holat Omborimda)", async () => {
    const counted = purchaseDetail({ purchase: purchaseRow({ stage: "received", state: "in_stock", path: supplyPath("in_stock", { in_transit: "2026-10-02", in_stock: todayTashkent() }) }) });
    const { api } = await renderAt(DETAIL, { [purchaseRoute("PATCH", PURCHASE_1)]: () => json(200, counted) });
    fireEvent.click(await screen.findByRole("button", { name: "Tovar keldi — bugun" }));
    await waitFor(() => expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))).toHaveLength(1));
    expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))[0]).toEqual({ dates: { received: todayTashkent() } });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Tovar keldi — bugun" })).toBeNull());
    expect(screen.getAllByText("Omborimda").length).toBeGreaterThan(0);
  });

  it("sanalar: tartib buzilsa saqlab bo'lmaydi; faqat o'zgargan sanalar yuboriladi", async () => {
    const { api } = await renderAt(DETAIL, { [purchaseRoute("PATCH", PURCHASE_1)]: () => json(200, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Sanalar" }));
    const dialog = await screen.findByRole("dialog", { name: "Xarid sanalari" });
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-01" } });
    const save = within(dialog).getByRole("button", { name: "Sanalarni saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(within(dialog).getByText(/Sanalar tartibi buzilgan/)).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Toshkentga keldi/), { target: { value: "2026-10-27" } });
    fireEvent.change(within(dialog).getByLabelText(/^Toʻlandi/), { target: { value: "" } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))).toHaveLength(1));
    expect(bodiesOf(api, purchaseRoute("PATCH", PURCHASE_1))[0]).toEqual({ dates: { paid: null, arrived: "2026-10-27" } });
  });

  it("tovar qo'shish: yangi tovar (havola, variant), qabul bo'sh — null", async () => {
    const route = purchaseSubRoute("POST", PURCHASE_1, "lines");
    const { api } = await renderAt(DETAIL, { [route]: () => json(201, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Tovar qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Tovar qoʻshish" });
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

  it("tovar qo'shish: hamma SKU ro'yxatda (arxivlangan va bloklangan ham), bir nechtasi bitta so'rovda", async () => {
    const route = purchaseSubRoute("POST", PURCHASE_1, "lines/bulk");
    const { api } = await renderAt(DETAIL, { [route]: () => json(201, purchaseDetail()) });
    fireEvent.click(await screen.findByRole("button", { name: "Tovar qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Tovar qoʻshish" });
    const box = await within(dialog).findByRole("combobox", { name: "Tovar" });
    await waitFor(() => expect((box as HTMLInputElement).disabled).toBe(false));
    fireEvent.focus(box);
    const options = within(await screen.findByRole("listbox")).getAllByRole("option");
    expect(options).toHaveLength(PICKER_ROWS.length); // hech narsa holat bo'yicha yashirilmagan
    const texts = options.map((o) => o.textContent ?? "");
    expect(texts.find((x) => x.includes("ARCHIVED"))).toContain("Koʻylak");
    expect(texts.find((x) => x.includes("BLOCKED"))).toContain("EL-ONE");
    expect(texts.find((x) => x.includes("Mashina"))).toContain("partiyada bor");
    expect(texts.find((x) => x.includes("Eski tovar"))).toContain("SKUʼsiz tovar");
    fireEvent.mouseDown(options.find((o) => o.textContent?.includes("ARCHIVED"))!);
    fireEvent.focus(box);
    fireEvent.mouseDown(within(await screen.findByRole("listbox")).getAllByRole("option").find((o) => o.textContent?.includes("BLOCKED"))!);
    const qty = within(dialog).getAllByLabelText("Dona");
    expect(qty).toHaveLength(2);
    fireEvent.change(qty[0]!, { target: { value: "10" } });
    fireEvent.change(qty[1]!, { target: { value: "20" } });
    fireEvent.change(within(dialog).getByLabelText(/^Dona narxi/), { target: { value: "3" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "2 ta tovar qoʻshish" }));
    await waitFor(() => expect(bodiesOf(api, route)).toHaveLength(1));
    expect(bodiesOf(api, route)[0]).toMatchObject({
      lines: [
        { sku_id: SKU_ARCHIVED, ordered_qty: 10, unit_price: "3", currency: "CNY" },
        { sku_id: SKU_BLOCKED, ordered_qty: 20, unit_price: "3", currency: "CNY" },
      ],
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("zaxira bozor kursi: kurs yonida «bozor kursi, Markaziy bank emas», lotda taxminiy belgi", async () => {
    const detail = purchaseDetail({
      components: [component({ applied_rate: "1650.500000", rate_source: "market", rate_day: "2026-10-03" })],
      purchase: purchaseRow({ flags: ["market_rate"] }),
      lines: [line({ flags: ["market_rate"] })],
    });
    await renderAt(DETAIL, { [purchaseRoute("GET", PURCHASE_1)]: () => json(200, detail) });
    const comps = await screen.findByRole("table", { name: "Xarajat komponentlari" });
    expect(within(comps).getByText(/bozor kursi, Markaziy bank emas/)).toBeTruthy();
    expect(within(comps).queryByText(/Markaziy bank\b(?! emas)/)).toBeNull();
    expect(screen.getByText(/Markaziy bank kursi serverga yetib kelmadi/)).toBeTruthy();
  });

  it("xarajat: kartadan yechilgan summa (effektiv kurs), tanlangan tovarlar; tahrirlash va o'chirish", async () => {
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
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Hamma tovarlar" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Yangi oʻyinchoq/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Xarajatni saqlash" }));
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
      cost_type_id: null,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const comps = screen.getByRole("table", { name: "Xarajat komponentlari" });
    fireEvent.click(within(comps).getByRole("button", { name: "Tahrirlash: Tovar" }));
    const edit = await screen.findByRole("dialog", { name: "Xarajatni tahrirlash" });
    fireEvent.click(within(edit).getByRole("radio", { name: "Qoʻlda kurs" }));
    fireEvent.change(within(edit).getByLabelText(/^1 birlik/), { target: { value: "1810" } });
    fireEvent.click(within(edit).getByRole("button", { name: "Xarajatni saqlash" }));
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
    fireEvent.click(within(screen.getByRole("table", { name: "Partiyadagi tovarlar" })).getByRole("button", { name: "Oʻchirish: Mashina" }));
    expect(await screen.findByText(/Bu tovar xarajatda alohida tanlangan/)).toBeTruthy();
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
    const lines = await screen.findByRole("table", { name: "Partiyadagi tovarlar" });
    expect(within(lines).queryByRole("columnheader", { name: "Narx" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Xarajat komponentlari" })).toBeNull();
    expect(screen.getByText("Summalar koʻrinmaydi.")).toBeTruthy();
    fireEvent.click(within(lines).getByRole("button", { name: "Tahrirlash: Mashina" }));
    const dialog = await screen.findByRole("dialog", { name: "Tovarni tahrirlash" });
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
    await screen.findByRole("table", { name: "Partiyadagi tovarlar" });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
