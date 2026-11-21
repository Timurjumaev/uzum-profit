// Oylik hisobot (B7.3): raqamlar API'dan (Foyda bilan bir hisob), "Dastlabki" / "Yakuniy" holat va Jarayondagi buyurtmalar, oy almashtirish,
// chop etish tugmasi, hamma bo'lim chiqadi. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { dashboardData, json, ME, ME_ROUTE, mockApi, ORG_ID, pnlData, type Routes } from "../../test/api";

const ROUTE = `GET /api/v1/orgs/${ORG_ID}/reports/monthly`;
const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[  ]/g, " ");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function report(over: Record<string, unknown> = {}) {
  const dash = dashboardData();
  const pnl = pnlData();
  return {
    month: "2026-10-01",
    period: { start: "2026-10-01", end: "2026-10-31", days: 31 },
    previous: { start: "2026-09-01", end: "2026-09-30", days: 30 },
    month_over: true,
    status: "final",
    processing_lines: 0,
    processing_revenue: "0.00",
    statement: pnl.statement,
    rows: pnl.rows,
    flow: dash.summary.flow,
    top: dash.top,
    bottom: dash.bottom,
    frozen_money: "12000000.00",
    in_transit_value: "3000000.00",
    ...over,
  };
}

async function renderReport(routes: Routes = {}) {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: "uz-Latn" } }),
    [ROUTE]: () => json(200, report()),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/reports"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: /Oylik hisobot — / });
  return api;
}

describe("oylik hisobot", () => {
  it("yakuniy hisobot: raqamlar API'dan, hamma bo'lim, tovardagi pul", async () => {
    await renderReport();
    expect(screen.getByText("Yakuniy")).toBeTruthy();
    expect(screen.queryByText("Hisobot dastlabki — raqamlar oʻzgarishi mumkin")).toBeNull();
    expect(norm(screen.getByTestId("report-profit").textContent!)).toBe(norm(f.money(pnlData().statement.net_profit)));
    expect(screen.getByRole("heading", { name: "Hisob varagʻi" })).toBeTruthy();
    expect(screen.getByRole("table", { name: "Hisob varagʻi" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Eng foydali SKUʼlar" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Uzum xarajatlari (toifalar boʻyicha)" })).toBeTruthy();
    expect(norm(screen.getByTestId("report-frozen").textContent!)).toBe(norm(f.money("12000000.00")));
    expect(screen.getByRole("columnheader", { name: "Oldingi oy" })).toBeTruthy();
  });

  it("dastlabki: Jarayondagi buyurtmalar soni va summasi ko'rsatiladi", async () => {
    await renderReport({ [ROUTE]: () => json(200, report({ status: "preliminary", processing_lines: 7, processing_revenue: "2500000.00" })) });
    expect(screen.getByText("Dastlabki")).toBeTruthy();
    const banner = screen.getByText("Hisobot dastlabki — raqamlar oʻzgarishi mumkin").closest("div")!;
    expect(norm(banner.parentElement!.textContent!)).toContain("7 ta buyurtma");
    expect(norm(banner.parentElement!.textContent!)).toContain(norm(f.money("2500000.00")));
  });

  it("oy almashtirish — so'rov oldingi oy bilan; chop etish — window.print", async () => {
    const api = await renderReport();
    fireEvent.click(screen.getByRole("button", { name: "Oldingi oy" }));
    await waitFor(() => expect(api.fetch.mock.calls.some(([r]) => new URL((r as Request).url).searchParams.get("month") === "2026-09-01")).toBe(true));
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    fireEvent.click(await screen.findByRole("button", { name: "Chop etish / PDF" }));
    expect(print).toHaveBeenCalledTimes(1);
    expect(within(screen.getByRole("group", { name: "Oy" })).getByTestId("report-month")).toBeTruthy();
  });
});
