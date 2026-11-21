// Reja-fakt (M12, B5.8): maqsadlar API'dan, tashkilot va do'kon guruhlari, prognoz va holat belgisi, oy almashtirish,
// maqsad belgilash va o'chirish. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { GOALS_ROUTE, GOALS_SET_ROUTE, json, ME, ME_ROUTE, mockApi, type Routes } from "../../test/api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const goal = (over: Record<string, unknown> = {}) => ({
  id: "g1",
  shop_id: null,
  metric: "revenue",
  target: "10000000.00",
  fact: "2500000.00",
  forecast: "8000000.00",
  percent: "25.0",
  forecast_percent: "80.0",
  deviation_pct: "-20.0",
  status: "behind",
  ...over,
});

const goals = (list: unknown[], month = "2026-11-01") => ({ month, days_in_month: 30, elapsed_days: 10, shops: [{ id: "shop-1", name: "byDurii" }], goals: list });

async function renderPage(routes: Routes = {}) {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: "uz-Latn" } }),
    [GOALS_ROUTE]: (request: Request) => json(200, goals([goal(), goal({ id: "g2", shop_id: "shop-1", metric: "units", target: "100.00", fact: "40.00", forecast: null, percent: "40.0", forecast_percent: null, deviation_pct: null, status: "unknown" })], new URL(request.url).searchParams.get("month") ?? "2026-11-01")),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/goals"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Reja-fakt" });
  return api;
}

describe("reja-fakt", () => {
  it("maqsadlar tashkilot va do'kon bo'yicha: bajarilish, prognoz va holat belgisi", async () => {
    await renderPage();
    const revenue = await screen.findByTestId("goal-revenue");
    expect(revenue.textContent).toContain("25"); // bajarilish %
    expect(revenue.textContent).toContain("Orqada"); // prognoz −20% (F59: 15% dan ko'p)
    expect(revenue.textContent).toContain("Oy oxiri prognozi");
    const units = screen.getByTestId("goal-units");
    expect(units.textContent).toContain("Prognoz hali yoʻq");
    expect(units.textContent).toContain("Noaniq");
    expect(screen.getByRole("region", { name: "byDurii" })).toBeTruthy(); // do'kon guruhi
    expect(screen.getByRole("region", { name: "Butun tashkilot" })).toBeTruthy();
  });

  it("oy almashtirish — so'rov keyingi oy bilan; maqsad belgilash PUT yuboradi", async () => {
    const api = await renderPage({ [GOALS_SET_ROUTE]: () => json(200, goal()) });
    fireEvent.click(await screen.findByRole("button", { name: "Keyingi oy" }));
    await waitFor(() => expect(api.fetch.mock.calls.some(([r]) => new URL((r as Request).url).searchParams.get("month") === "2026-12-01")).toBe(true));
    fireEvent.change(await screen.findByLabelText("Maqsad"), { target: { value: "5000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodies.some((b) => b.key === GOALS_SET_ROUTE)).toBe(true));
    const body = api.bodies.find((b) => b.key === GOALS_SET_ROUTE)!.body as Record<string, unknown>;
    expect(body).toMatchObject({ metric: "revenue", target: "5000000", shop_id: null });
    expect(String(body.month)).toMatch(/^2026-12/);
  });

  it("maqsad yo'q — bo'sh holat", async () => {
    await renderPage({ [GOALS_ROUTE]: () => json(200, goals([])) });
    expect(await screen.findByText("Bu oy uchun maqsad yoʻq")).toBeTruthy();
  });
});
