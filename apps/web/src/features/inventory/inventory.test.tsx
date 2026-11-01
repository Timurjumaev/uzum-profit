// Ombor (M10, B4.7): jadval (holat, joylar, tezlik, zaxira kunlari, buyurtma sanasi, tavsiya miqdor), KPI, holat guruhi va
// qidiruv URL'da, "Xarid yaratish" (qoralama + qator), hisobdan chiqarish (yozuv, tarix, qaytarish), omborchi — summasiz,
// buxgalter — faqat ko'radi. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { todayTashkent } from "../../lib/dates";
import { formatterFor } from "../../lib/format";
import {
  INVENTORY_ROUTE,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  PURCHASE_CREATE_ROUTE,
  purchaseRoute,
  purchaseSubRoute,
  STOCK_MOVE_CREATE_ROUTE,
  stockMoveDeleteRoute,
  stockMovesRoute,
  type Routes,
} from "../../test/api";
import { deadRow, inventoryData, ITEM_CRIT, move, MOVE_1, stockRow } from "../../test/inventory";
import { purchaseDetail, PURCHASE_1 } from "../../test/purchases";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [INVENTORY_ROUTE]: () => json(200, inventoryData()),
    [stockMovesRoute(ITEM_CRIT)]: () => json(200, { items: [move()] }),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;
const queryOf = (api: ReturnType<typeof mockApi>, last = true) => {
  const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname.endsWith("/inventory"));
  return (last ? urls[urls.length - 1] : urls[0])!.searchParams;
};

describe("ombor jadvali", () => {
  it("qatorlar: holat, Uzumda, joylar, tezlik, zaxira, buyurtma sanasi, tavsiya va qiymat", async () => {
    await renderAt("/inventory");
    const table = await screen.findByRole("table", { name: "Qoldiq jadvali" });
    const [crit, dead] = within(table).getAllByRole("row").slice(1);
    const c = norm(crit!.textContent!);
    expect(c).toContain("Mashina");
    expect(c).toContain("Kritik");
    expect(c).toContain("FBO 8 · FBS 2");
    expect(c).toContain("Xitoyda: 20");
    expect(c).toContain("Yoʻlda: 30");
    expect(c).toContain("Omborimda: 15");
    expect(c).toContain("Brak: 1");
    expect(c).toContain("2,00"); // tezlik F23
    expect(c).toContain("Hozir"); // buyurtma kechikkan (F27)
    expect(c).toContain("90"); // tavsiya miqdor
    expect(c).toContain(norm(f.currency("90000.00", "CNY"))); // byudjet CNY
    expect(c).toContain(norm(f.money("1000000.00", { unit: false })));
    const d = norm(dead!.textContent!);
    expect(d).toContain("Harakatsiz");
    expect(d).toContain("Sekin"); // F30
    expect(within(dead!).queryByRole("button", { name: "Xarid yaratish" })).toBeNull(); // tavsiya yo'q
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Ombor");
  });

  it("KPI: muzlagan pul, yo'ldagi tovar, o'z omborim, o'rtacha sotilish muddati; holat sonlari tabda", async () => {
    await renderAt("/inventory");
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    const page = norm(document.body.textContent!);
    expect(page).toContain(norm(f.money("8600000.00")));
    expect(page).toContain("50 dona"); // Xitoyda 20 + yo'lda 30
    expect(page).toContain(norm(f.money(6_000_000))); // yo'ldagi qiymat
    expect(page).toContain("15 dona");
    expect(page).toContain("13 kun"); // 12,5 → 13
    expect(screen.getByRole("tab", { name: /Kritik/ }).textContent).toContain("1");
    expect(screen.getByRole("tab", { name: /Hammasi/ }).textContent).toContain("2");
  });

  it("KPI: postavkadagi tovar ham yo'lda (ADR-034)", async () => {
    const base = inventoryData();
    const totals = { ...base.totals, units: { ...base.totals.units, inbound: 744 }, frozen_money: { ...base.totals.frozen_money!, inbound: "1000000.00" } };
    await renderAt("/inventory", { [INVENTORY_ROUTE]: () => json(200, { ...base, totals }) });
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    const page = norm(document.body.textContent!);
    expect(page).toContain(norm(`${f.number(794)} dona`)); // 20 + 30 + 744
    expect(page).toContain(norm(`shundan postavkada ${f.number(744)} dona`));
    expect(page).toContain(norm(f.money(7_000_000))); // 6 000 000 + 1 000 000
  });

  it("holat guruhi URL'da va API'ga `status` bo'lib boradi; qidiruv — `q`", async () => {
    const { api, history } = await renderAt("/inventory");
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    fireEvent.click(screen.getByRole("tab", { name: /Kritik/ }));
    await waitFor(() => expect(history.location.search).toContain("status=critical"));
    await waitFor(() => expect(queryOf(api).get("status")).toBe("critical"));
    fireEvent.change(screen.getByRole("searchbox", { name: "Qidiruv" }), { target: { value: "mashina" } });
    await waitFor(() => expect(history.location.search).toContain("q=mashina"));
    await waitFor(() => expect(queryOf(api).get("q")).toBe("mashina"));
    expect(queryOf(api).get("status")).toBe("critical");
  });

  it("bo'sh holat: filtr bilan — tozalash taklifi; filtrsiz — sinxron haqida", async () => {
    const empty = { [INVENTORY_ROUTE]: () => json(200, inventoryData({ items: [], total: 0, totals: { ...inventoryData().totals, statuses: {} } })) };
    await renderAt("/inventory?status=good", empty);
    expect(await screen.findByText("Bu filtrga mos SKU yoʻq")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Filtrni tozalash" })).toBeTruthy();
    cleanup();
    await renderAt("/inventory", empty);
    expect(await screen.findByText("Qoldiq maʼlumoti yoʻq")).toBeTruthy();
  });

  it("xato — qayta urinish tugmasi", async () => {
    await renderAt("/inventory", { [INVENTORY_ROUTE]: () => problem(403, "forbidden") });
    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeTruthy();
  });

  it("tannarxsiz SKU — ogohlantirish banneri", async () => {
    const data = inventoryData();
    await renderAt("/inventory", { [INVENTORY_ROUTE]: () => json(200, { ...data, totals: { ...data.totals, uncosted: 3 } }) });
    expect(await screen.findByText("3 ta SKU tannarxsiz")).toBeTruthy();
  });

  it("yana yuklash: keyingi sahifa kursor bilan", async () => {
    const pages = [() => json(200, inventoryData({ next_cursor: "abc" })), () => json(200, inventoryData({ items: [stockRow({ sku_id: "d3333333-3333-4333-8333-333333333333", product_title: "Uchinchi" })], next_cursor: null }))];
    const { api } = await renderAt("/inventory", { [INVENTORY_ROUTE]: pages });
    fireEvent.click(await screen.findByRole("button", { name: "Yana yuklash" }));
    expect(await screen.findByText("Uchinchi")).toBeTruthy();
    expect(queryOf(api).get("cursor")).toBe("abc");
  });
});

describe("rollar", () => {
  it("omborchi: summasiz — qiymat bannerda, pul KPI yo'q; amallar bor", async () => {
    const data = inventoryData();
    const hidden = inventoryData({
      items: data.items.map((r) => ({ ...r, unit_cost: null, stock_value: null, reorder: r.reorder ? { ...r.reorder, budget: null } : null })),
      totals: { ...data.totals, frozen_money: null, frozen_total: null },
    });
    await renderAt("/inventory", { [INVENTORY_ROUTE]: () => json(200, hidden) }, "warehouse");
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    expect(screen.getByText("Summalar sizga koʻrinmaydi")).toBeTruthy();
    expect(screen.queryByText("Muzlagan pul")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Xarid yaratish" })).toHaveLength(1);
    expect(norm(document.body.textContent!)).not.toContain("CNY");
  });

  it("buxgalter faqat ko'radi: amal tugmalari yo'q", async () => {
    await renderAt("/inventory", {}, "accountant");
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    expect(screen.queryByRole("button", { name: "Xarid yaratish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Hisobdan chiqarish" })).toBeNull();
  });
});

describe("xarid yaratish", () => {
  it("qoralama xarid + tavsiya miqdorli qator yaratadi va xarid sahifasiga o'tadi", async () => {
    const { api, history } = await renderAt("/inventory", {
      [PURCHASE_CREATE_ROUTE]: () => json(201, purchaseDetail()),
      [purchaseSubRoute("POST", PURCHASE_1, "lines")]: () => json(201, purchaseDetail()),
      [purchaseRoute("GET", PURCHASE_1)]: () => json(200, purchaseDetail()),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Xarid yaratish" }));
    await waitFor(() => expect(history.location.pathname).toBe(`/purchases/${PURCHASE_1}`));
    expect(bodiesOf(api, PURCHASE_CREATE_ROUTE)[0]).toEqual({ title: "Qayta buyurtma: Mashina" });
    expect(bodiesOf(api, purchaseSubRoute("POST", PURCHASE_1, "lines"))[0]).toEqual({ item_id: ITEM_CRIT, ordered_qty: 90 });
  });

  it("qator yaratilmasa qoralama o'chiriladi (ortiqcha xarid qolmaydi)", async () => {
    const { api, history } = await renderAt("/inventory", {
      [PURCHASE_CREATE_ROUTE]: () => json(201, purchaseDetail()),
      [purchaseSubRoute("POST", PURCHASE_1, "lines")]: () => problem(404, "item_not_found"),
      [purchaseRoute("DELETE", PURCHASE_1)]: () => new Response(null, { status: 204 }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Xarid yaratish" }));
    await waitFor(() => expect(api.count(purchaseRoute("DELETE", PURCHASE_1))).toBe(1));
    expect(history.location.pathname).toBe("/inventory");
  });
});

describe("hisobdan chiqarish", () => {
  it("yozuv: dona musbat bo'lguncha saqlab bo'lmaydi; tanasi to'g'ri; tarix ko'rinadi", async () => {
    const { api } = await renderAt("/inventory", { [STOCK_MOVE_CREATE_ROUTE]: () => json(201, move({ qty: 4 })) });
    fireEvent.click((await screen.findAllByRole("button", { name: "Hisobdan chiqarish" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Hisobdan chiqarish: Mashina" });
    expect(await within(dialog).findByText(/Qabulda brak/)).toBeTruthy(); // oxirgi yozuvlar
    const save = within(dialog).getByRole("button", { name: "Yozuvni saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "-2" } });
    expect(save.disabled).toBe(true); // hisobdan chiqarish — musbat
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "4" } });
    fireEvent.change(within(dialog).getByLabelText(/^Izoh/), { target: { value: " Yoʻqolgan " } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, STOCK_MOVE_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, STOCK_MOVE_CREATE_ROUTE)[0]).toEqual({ item_id: ITEM_CRIT, kind: "writeoff", qty: 4, day: todayTashkent(), note: "Yoʻqolgan" });
  });

  it("inventarizatsiya tuzatishi manfiy bo'lishi mumkin, 0 — yo'q", async () => {
    const { api } = await renderAt("/inventory", { [STOCK_MOVE_CREATE_ROUTE]: () => json(201, move({ kind: "adjust", qty: -3 })) });
    fireEvent.click((await screen.findAllByRole("button", { name: "Hisobdan chiqarish" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Hisobdan chiqarish: Mashina" });
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "adjust" } });
    const save = within(dialog).getByRole("button", { name: "Yozuvni saqlash" }) as HTMLButtonElement;
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "0" } });
    expect(save.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "-3" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, STOCK_MOVE_CREATE_ROUTE)[0]).toMatchObject({ kind: "adjust", qty: -3, note: null }));
  });

  it("eski yozuvni o'chirib qaytarish; xato bannerda", async () => {
    const { api } = await renderAt("/inventory", { [stockMoveDeleteRoute(MOVE_1)]: [() => problem(403, "forbidden"), () => new Response(null, { status: 204 })] });
    fireEvent.click((await screen.findAllByRole("button", { name: "Hisobdan chiqarish" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Hisobdan chiqarish: Mashina" });
    const remove = await within(dialog).findByRole("button", { name: /yozuvini oʻchirish/ });
    fireEvent.click(remove);
    expect(await within(dialog).findByRole("alert")).toBeTruthy();
    fireEvent.click(remove);
    await waitFor(() => expect(api.count(stockMoveDeleteRoute(MOVE_1))).toBe(2));
  });

  it("tovarsiz SKU'da amal yo'q", async () => {
    await renderAt("/inventory", { [INVENTORY_ROUTE]: () => json(200, inventoryData({ items: [deadRow({ item_id: null })] })) });
    await screen.findByRole("table", { name: "Qoldiq jadvali" });
    expect(screen.queryByRole("button", { name: "Hisobdan chiqarish" })).toBeNull();
  });
});

it("a11y: jiddiy buzilish yo'q", async () => {
  await renderAt("/inventory");
  await screen.findByRole("table", { name: "Qoldiq jadvali" });
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious").map((v) => v.id)).toEqual([]);
});
