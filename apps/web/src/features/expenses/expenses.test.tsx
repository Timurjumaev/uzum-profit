// Xarajatlar (M8, B4.5): Uzum xarajatlari (F9 — toifalar, jarimalar, ro'yxat, P&L'ga kirmaganlari) va o'z xarajatlarim
// (F10 — qo'shish: bir martalik, davr, takroriy; tahrirlash; o'chirish; ruxsatlar). Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { EXPENSES_ROUTE, json, ME, ME_ROUTE, mockApi, OWN_CATEGORIES_ROUTE, OWN_CREATE_ROUTE, ownRoute, problem, type Routes } from "../../test/api";
import { expensesData, OWN_1, ownItem, uzumItem } from "../../test/expenses";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));
const PATH = "/expenses?from=2026-10-01&to=2026-10-20";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [EXPENSES_ROUTE]: () => json(200, expensesData()),
    [OWN_CATEGORIES_ROUTE]: () => json(200, { items: ["ijara", "internet", "ish haqi"] }),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("Uzum xarajatlari", () => {
  it("toifalar (ishorali, jami = F9), jarimalar, ro'yxat; P&L'ga kirmagan yozuv belgilanadi", async () => {
    await renderAt(PATH);
    const cats = await screen.findByRole("table", { name: "Toifalar boʻyicha" });
    const rows = within(cats).getAllByRole("row");
    expect(within(rows[1]!).getByText("Reklama")).toBeTruthy(); // eng katta birinchi
    expect(within(cats).getByText(n("-10000.00"))).toBeTruthy(); // kompensatsiya — minus
    expect(within(cats).getByText(n("240000.00"))).toBeTruthy(); // jami API'dan
    const fines = screen.getByRole("table", { name: "Eng katta jarimalar" });
    expect(within(fines).getByText("Jarima: kechikish")).toBeTruthy();
    const list = await screen.findByRole("table", { name: "Barcha yozuvlar" });
    expect(await within(list).findByText("Foydaga kirmaydi")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Xarajatlar");
  });

  it("toifa filtri ro'yxat so'rovini o'zgartiradi; 'Yana yuklash' kursor bilan", async () => {
    let calls = 0;
    const { api } = await renderAt(PATH, {
      [EXPENSES_ROUTE]: (req) => {
        calls += 1;
        const u = new URL(req.url);
        if (u.searchParams.get("cursor") === "C2") return json(200, expensesData({ items: [uzumItem({ id: "z10", name: "Ikkinchi sahifa" })], next_cursor: null }));
        if (u.searchParams.get("category") === "fine") return json(200, expensesData({ items: [uzumItem({ id: "z9", name: "Faqat jarima" })], next_cursor: "C2" }));
        return json(200, expensesData());
      },
    });
    await screen.findByRole("table", { name: "Barcha yozuvlar" });
    fireEvent.change(screen.getByLabelText("Toifa"), { target: { value: "fine" } });
    expect(await screen.findByText("Faqat jarima")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yana yuklash" }));
    expect(await screen.findByText("Ikkinchi sahifa")).toBeTruthy();
    const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url));
    expect(urls.some((u) => u.searchParams.get("category") === "fine")).toBe(true);
    expect(urls.some((u) => u.searchParams.get("cursor") === "C2")).toBe(true);
    expect(calls).toBeGreaterThan(2);
  });

  it("bo'sh davr — bo'sh holat; xato — qayta urinish", async () => {
    await renderAt(PATH, { [EXPENSES_ROUTE]: () => json(200, expensesData({ uzum: [], uzum_total: "0.00", by_month: [], fines: [], items: [] })) });
    expect(await screen.findByText("Bu davrda Uzum xarajatlari yoʻq")).toBeTruthy();
    cleanup();
    await renderAt(PATH, { [EXPENSES_ROUTE]: () => problem(403, "forbidden") });
    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeTruthy();
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt(PATH);
    await screen.findByRole("table", { name: "Toifalar boʻyicha" });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});

describe("oʻz xarajatlarim", () => {
  const OWN = `${PATH}&section=own`;

  it("bo'lim URL'da; jadval: davrdagi qism, takroriy belgisi, do'kon nomi; jami API'dan", async () => {
    const { history } = await renderAt(PATH);
    await screen.findByRole("table", { name: "Toifalar boʻyicha" });
    fireEvent.click(screen.getByRole("tab", { name: "Oʻz xarajatlarim" }));
    await waitFor(() => expect(history.location.search).toContain("section=own"));
    const list = await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    expect(within(list).getByText(n("200000.00"))).toBeTruthy(); // davrdagi qism
    expect(within(list).getByText(n("310000.00"))).toBeTruthy(); // to'liq summa
    expect(within(list).getByText("Har oy")).toBeTruthy();
    expect(within(list).getByText("Durii")).toBeTruthy();
    expect(norm(screen.getByRole("tabpanel").textContent!)).toContain(norm(f.money("300000.00")));
  });

  it("qo'shish: bir martalik — end_on yuborilmaydi; toifa yangi bo'lsa nomi bilan; ro'yxat qayta so'raladi", async () => {
    const { api } = await renderAt(OWN, { [OWN_CREATE_ROUTE]: () => json(201, [ownItem()]) });
    await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    fireEvent.click(screen.getByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Saqlash" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText("Toifa"), { target: { value: "__new" } });
    fireEvent.change(within(dialog).getByLabelText("Yangi toifa nomi"), { target: { value: "  sug'urta " } });
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "50000" } });
    fireEvent.change(within(dialog).getByLabelText("Sana"), { target: { value: "2026-10-10" } });
    expect((submit as HTMLButtonElement).disabled).toBe(false);
    const before = api.count(`GET /api/v1/orgs/${ME.orgs[0]!.id}/expenses`);
    fireEvent.click(submit);
    await waitFor(() => expect(bodiesOf(api, OWN_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, OWN_CREATE_ROUTE)[0]).toMatchObject({ category: "sug'urta", amount: "50000", start_on: "2026-10-10", end_on: null, repeat_months: 1, shop_id: null, note: null });
    await waitFor(() => expect(api.count(`GET /api/v1/orgs/${ME.orgs[0]!.id}/expenses`)).toBeGreaterThan(before));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("davr (amortizatsiya) va takroriy: tegishli maydonlar va tanasi", async () => {
    const { api } = await renderAt(OWN, { [OWN_CREATE_ROUTE]: () => json(201, [ownItem()]) });
    await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    fireEvent.click(screen.getByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("option", { name: "ijara" });
    fireEvent.change(within(dialog).getByLabelText("Toifa"), { target: { value: "ijara" } });
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "1200000" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Davr (amortizatsiya)" }));
    fireEvent.change(within(dialog).getByLabelText("Boshlanishi"), { target: { value: "2026-01-01" } });
    fireEvent.change(within(dialog).getByLabelText("Tugashi"), { target: { value: "2026-12-31" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, OWN_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, OWN_CREATE_ROUTE)[0]).toMatchObject({ start_on: "2026-01-01", end_on: "2026-12-31", repeat_months: 1 });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Xarajat qoʻshish" }));
    const second = await screen.findByRole("dialog");
    await within(second).findByRole("option", { name: "internet" });
    fireEvent.change(within(second).getByLabelText("Toifa"), { target: { value: "internet" } });
    fireEvent.change(within(second).getByLabelText(/^Summa/), { target: { value: "100000" } });
    fireEvent.click(within(second).getByRole("radio", { name: "Har oy takrorlanadi" }));
    fireEvent.change(within(second).getByLabelText("Birinchi sana"), { target: { value: "2026-11-05" } });
    fireEvent.change(within(second).getByLabelText("Necha oy"), { target: { value: "6" } });
    fireEvent.click(within(second).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, OWN_CREATE_ROUTE)).toHaveLength(2));
    expect(bodiesOf(api, OWN_CREATE_ROUTE)[1]).toMatchObject({ start_on: "2026-11-05", end_on: null, repeat_months: 6 });
  });

  it("tahrirlash: mavjud qiymatlar bilan ochiladi, PATCH yuboriladi; o'chirish — DELETE", async () => {
    const { api } = await renderAt(OWN, {
      [ownRoute("PATCH", OWN_1)]: () => json(200, ownItem()),
      [ownRoute("DELETE", OWN_1)]: () => new Response(null, { status: 204 }),
    });
    const list = await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    fireEvent.click(within(list).getAllByRole("button", { name: /^Tahrirlash/ })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Xarajatni tahrirlash" });
    expect(within(dialog).queryByRole("radio", { name: "Har oy takrorlanadi" })).toBeNull();
    expect((within(dialog).getByLabelText("Toifa") as HTMLSelectElement).value).toBe("ijara");
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "400000" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(ownRoute("PATCH", OWN_1))).toHaveLength(1));
    expect(api.bodiesOf(ownRoute("PATCH", OWN_1))[0]).toMatchObject({ category: "ijara", amount: "400000", start_on: "2026-10-01", end_on: "2026-10-31" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(within(list).getAllByRole("button", { name: /^Oʻchirish/ })[0]!);
    await waitFor(() => expect(api.count(ownRoute("DELETE", OWN_1))).toBe(1));
  });

  it("server xatosi shaklda ko'rsatiladi; buxgalter faqat ko'radi (qo'shish va amallar yo'q)", async () => {
    await renderAt(OWN, { [OWN_CREATE_ROUTE]: () => problem(422, "bad_period") });
    await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    fireEvent.click(screen.getByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("option", { name: "ijara" });
    fireEvent.change(within(dialog).getByLabelText("Toifa"), { target: { value: "ijara" } });
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "1000" } });
    fireEvent.change(within(dialog).getByLabelText("Sana"), { target: { value: "2026-10-10" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    expect(await within(dialog).findByRole("alert")).toBeTruthy();
    cleanup();
    await renderAt(OWN, {}, "accountant");
    const list = await screen.findByRole("table", { name: "Oʻz xarajatlarim roʻyxati" });
    expect(screen.queryByRole("button", { name: "Xarajat qoʻshish" })).toBeNull();
    expect(within(list).queryByRole("button", { name: /^Tahrirlash/ })).toBeNull();
  });

  it("o'z xarajati yo'q — bo'sh holat (menejer qo'sha oladi)", async () => {
    await renderAt(OWN, { [EXPENSES_ROUTE]: () => json(200, expensesData({ own: [], own_items: [], own_total: "0.00" })) });
    expect(await screen.findByText("Oʻz xarajatlaringiz yoʻq")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Xarajat qoʻshish" })).toBeTruthy();
  });
});
