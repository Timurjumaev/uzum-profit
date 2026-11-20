// "Pul oqimi" (B5.7, F38): KPI, kutilgan to'lovlar jadvali ("Taxminiy" / "Aniq"), jadval kiritilmagan holat, xato.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { json, ME, ME_ROUTE, mockApi, PAYOUT_FORECAST_ROUTE, problem, type Routes } from "../../test/api";
import { payoutForecast } from "../../test/payouts";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderCash(routes: Routes = {}) {
  mockApi({ [ME_ROUTE]: () => json(200, ME), [PAYOUT_FORECAST_ROUTE]: () => json(200, payoutForecast()), ...routes });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/cash"] }), "uz-Latn")} />);
}

describe("pul oqimi", () => {
  it("KPI va kutilgan to'lovlar: summa, haq, qo'lga tegadi, Taxminiy / Aniq; qoidalar serverdan", async () => {
    renderCash();
    expect(await screen.findByRole("heading", { level: 1, name: "Pul oqimi" })).toBeTruthy();
    const table = await screen.findByRole("table", { name: "Kutilayotgan toʻlovlar" });
    const [first, second] = within(table).getAllByRole("row").slice(1);
    const a = norm(first!.textContent!);
    expect(a).toContain(norm(f.money("1200000.00")));
    expect(a).toContain("Aniq");
    expect(norm(second!.textContent!)).toContain("Taxminiy");
    const page = norm(document.body.textContent!);
    expect(page).toContain("Yechishga tayyor");
    expect(page).toContain(norm(f.money("450000.00"))); // sana noma'lum
    expect(page).toContain("mijozga topshirilgandan 10 kun oʻtgach yechishga beriladi; ertaroq yechish — 2,5%");
  });

  it("jadval kiritilmagan — taxmin yo'q, Sozlamalarga havola", async () => {
    renderCash({ [PAYOUT_FORECAST_ROUTE]: () => json(200, payoutForecast({ schedule: null, fee_pct: null, events: [], available: "0", unknown_date: "0" })) });
    expect(await screen.findByText("Toʻlov jadvali kiritilmagan")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sozlamalarga oʻtish" }).getAttribute("href")).toBe("/settings");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("kutilgan to'lov yo'q — bo'sh holat; xato — sabab xato bannerida (sarlavha saqlanadi)", async () => {
    renderCash({ [PAYOUT_FORECAST_ROUTE]: () => json(200, payoutForecast({ events: [] })) });
    expect(await screen.findByText("Kutilayotgan toʻlov yoʻq", { selector: "h3" })).toBeTruthy();
    cleanup();
    renderCash({ [PAYOUT_FORECAST_ROUTE]: () => problem(403, "forbidden") });
    expect(await screen.findByRole("heading", { level: 1, name: "Pul oqimi" })).toBeTruthy();
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
