// Buyurtmalar (M7, B4.4): ro'yxat (holat filtri, "Bonus davri" belgisi, tannarxsiz belgisi, sahifalash), bekor va
// qaytish tahlili (F17, F18, sabablar, SKU bo'yicha, qaytim saqlash). Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { json, mockApi, ORDERS_ANALYSIS_ROUTE, ORG_ID, problem, SALES_ROUTE, type Routes } from "../../test/api";
import { analysisData, sale, salesData, SKU_X } from "../../test/orders";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));
const PATH = "/orders?from=2026-10-01&to=2026-10-20";
const CAPTION = "Buyurtmalar: sotuv qatorlari";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}) {
  const api = mockApi({
    [SALES_ROUTE]: () => json(200, salesData()),
    [ORDERS_ANALYSIS_ROUTE]: () => json(200, analysisData()),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const urls = (api: ReturnType<typeof mockApi>, route: string) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === route.split(" ")[1]);

describe("roʻyxat", () => {
  it("qatorlar: holat belgisi, bonus davri, tannarxsiz va taxminiy belgilar; yuqorida F17/F18 ulushi", async () => {
    await renderAt(PATH);
    const table = await screen.findByRole("table", { name: CAPTION });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Buyurtmalar");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    expect(within(rows[0]!).getByText("Yakunlangan")).toBeTruthy();
    expect(within(rows[0]!).getByText(n("310000.00"))).toBeTruthy();
    expect(within(rows[1]!).getByText("Bekor")).toBeTruthy();
    expect(within(rows[1]!).getAllByText("—").length).toBeGreaterThan(0); // tannarx va foyda noma'lum
    expect(within(rows[2]!).getByText("Bonus davri")).toBeTruthy();
    expect(within(rows[2]!).getByText("SKU bogʻlanmagan")).toBeTruthy();
    expect(within(rows[3]!).getByText("Jarayonda")).toBeTruthy();
    expect(within(rows[3]!).getByText("Taxminiy")).toBeTruthy();
    const summary = document.querySelector(".orders-summary")!.textContent!;
    expect(norm(summary)).toContain("13 dona yakunlandi");
    expect(summary).toContain(f.percent("0.277778"));
    expect(summary).toContain(f.percent("0.187500"));
  });

  it("so'rov: davr va limit; holat filtri URL'ga yoziladi va so'rovni o'zgartiradi", async () => {
    const { api, history } = await renderAt(PATH);
    await screen.findByRole("table", { name: CAPTION });
    const [first] = urls(api, SALES_ROUTE);
    expect(first!.searchParams.get("start")).toBe("2026-10-01");
    expect(first!.searchParams.get("end")).toBe("2026-10-20");
    expect(first!.searchParams.get("group")).toBeNull();
    expect(first!.searchParams.get("limit")).toBe("50");
    fireEvent.change(screen.getByLabelText("Holat"), { target: { value: "canceled" } });
    await waitFor(() => expect(history.location.search).toContain("group=canceled"));
    await waitFor(() => expect(urls(api, SALES_ROUTE).some((u) => u.searchParams.get("group") === "canceled")).toBe(true));
  });

  it("URL'dagi holat filtri qo'llanadi; noto'g'ri qiymat e'tiborsiz", async () => {
    const good = await renderAt(`${PATH}&group=processing`);
    await screen.findByRole("table", { name: CAPTION });
    expect(urls(good.api, SALES_ROUTE)[0]!.searchParams.get("group")).toBe("processing");
    cleanup();
    const bad = await renderAt(`${PATH}&group=hack`);
    await screen.findByRole("table", { name: CAPTION });
    expect(urls(bad.api, SALES_ROUTE)[0]!.searchParams.get("group")).toBeNull();
  });

  it("sahifalash: 'Yana yuklash' kursor bilan keyingi qatorlarni qo'shadi", async () => {
    const { api } = await renderAt(PATH, {
      [SALES_ROUTE]: [
        () => json(200, salesData({ items: [sale()], next_cursor: "CUR1" })),
        () => json(200, salesData({ items: [sale({ id: "s9", sku_title: "Ikkinchi sahifa" })], next_cursor: null })),
      ],
    });
    await screen.findByRole("table", { name: CAPTION });
    fireEvent.click(screen.getByRole("button", { name: "Yana yuklash" }));
    expect(await screen.findByText("Ikkinchi sahifa")).toBeTruthy();
    expect(urls(api, SALES_ROUTE)[1]!.searchParams.get("cursor")).toBe("CUR1");
    expect(screen.queryByRole("button", { name: "Yana yuklash" })).toBeNull();
  });

  it("bo'sh davr — bo'sh holat; xato — qayta urinish bannerı", async () => {
    await renderAt(PATH, { [SALES_ROUTE]: () => json(200, salesData({ items: [], summary: { units: 0, canceled: 0, returns: 0, cancel_share: null, return_share: null } })) });
    expect(await screen.findByText("Bu davrda buyurtma yoʻq")).toBeTruthy();
    cleanup();
    await renderAt(PATH, { [SALES_ROUTE]: () => problem(403, "forbidden") });
    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeTruthy();
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt(PATH);
    await screen.findByRole("table", { name: CAPTION });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});

describe("tahlil", () => {
  it("bo'limlar URL'da; bekor: ulush, topshirilgandan keyin, sabablar, SKU bo'yicha", async () => {
    const { history } = await renderAt(PATH);
    await screen.findByRole("table", { name: CAPTION });
    fireEvent.click(screen.getByRole("tab", { name: "Bekor boʻlish" }));
    await waitFor(() => expect(history.location.search).toContain("tab=cancel"));
    const panel = await screen.findByRole("tabpanel");
    await within(panel).findByRole("table", { name: "Bekor sabablari" });
    expect(within(panel).getByText(f.percent("0.277778"))).toBeTruthy();
    expect(within(panel).getByText("Topshirilgandan keyin bekor")).toBeTruthy();
    expect(norm(panel.textContent!)).toContain(f.percent("0.400000"));
    const causes = within(panel).getByRole("table", { name: "Bekor sabablari" });
    expect(within(causes).getByText("Mijoz fikrini oʻzgartirdi")).toBeTruthy();
    const skus = within(panel).getByRole("table", { name: "SKU boʻyicha" });
    const link = within(skus).getByRole("link", { name: "Oʻyinchoq mashina" });
    expect(link.getAttribute("href")).toContain(`/products/${SKU_X}`);
    expect(within(skus).queryByText("SKU bogʻlanmagan")).toBeNull();
  });

  it("qaytish: ulush, qaytim saqlash xarajati, sabab (sababsiz — 'Sabab ko'rsatilmagan'), bog'lanmagan SKU", async () => {
    await renderAt(`${PATH}&tab=returns`);
    const panel = await screen.findByRole("tabpanel");
    await within(panel).findByRole("table", { name: "Qaytish sabablari" });
    expect(within(panel).getByText(f.percent("0.187500"))).toBeTruthy();
    expect(norm(panel.textContent!)).toContain(norm(f.money("49000.00")));
    const causes = within(panel).getByRole("table", { name: "Qaytish sabablari" });
    expect(within(causes).getByText("Sifat yomon")).toBeTruthy();
    expect(within(causes).getByText("Sabab koʻrsatilmagan")).toBeTruthy();
    const skus = within(panel).getByRole("table", { name: "SKU boʻyicha" });
    expect(within(skus).getByText("SKU bogʻlanmagan")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Qaytarilish" }).getAttribute("aria-selected")).toBe("true");
  });

  it("noma'lum bo'lim e'tiborsiz — ro'yxat; ma'lumotsiz davr — bo'sh holat; xato — qayta urinish", async () => {
    await renderAt(`${PATH}&tab=hack`);
    await screen.findByRole("table", { name: CAPTION });
    cleanup();
    const empty = analysisData({
      summary: { units: 0, canceled: 0, returns: 0, cancel_share: null, return_share: null, canceled_after_issue: 0, after_issue_share: null, return_storage_cost: "0.00" },
      daily: [],
      by_sku: [],
      return_causes: [],
      cancel_causes: [],
    });
    await renderAt(`${PATH}&tab=cancel`, { [ORDERS_ANALYSIS_ROUTE]: () => json(200, empty) });
    expect(await screen.findByText("Bu davrda buyurtma yoʻq")).toBeTruthy();
    cleanup();
    await renderAt(`${PATH}&tab=cancel`, { [ORDERS_ANALYSIS_ROUTE]: () => problem(403, "forbidden") });
    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeTruthy();
  });

  it("so'rov davr va do'kon filtri bilan ketadi", async () => {
    const { api } = await renderAt(`${PATH}&tab=cancel`);
    const panel = await screen.findByRole("tabpanel");
    await within(panel).findByRole("table", { name: "Bekor sabablari" });
    const [req] = urls(api, ORDERS_ANALYSIS_ROUTE);
    expect(req!.pathname).toBe(`/api/v1/orgs/${ORG_ID}/orders/analysis`);
    expect(req!.searchParams.get("start")).toBe("2026-10-01");
    expect(req!.searchParams.get("end")).toBe("2026-10-20");
  });
});
