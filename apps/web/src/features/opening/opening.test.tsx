// Boshlang'ich holat sahifasi (B4.12, F41): jadval, qamrov, saqlash tanasi, sana almashsa taklif so'rovi, o'chirish,
// faqat ko'rish (buxgalter), axe. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, ME, ME_ROUTE, mockApi, ORG_ID, type Routes } from "../../test/api";
import { openingData } from "../../test/opening";

const ROUTE = `GET /api/v1/orgs/${ORG_ID}/opening`;
const PUT = `PUT /api/v1/orgs/${ORG_ID}/opening`;

const data = openingData;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage(routes: Routes = {}, role = "owner") {
  const api = mockApi({ [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }), [ROUTE]: () => json(200, data()), ...routes });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/opening"] }), "uz-Latn")} />);
  return api;
}

const norm = (text: string | null) => (text ?? "").replace(/[\u00A0\u202F]/g, " ");

describe("boshlang'ich holat", () => {
  it("jadval, qamrov va ogohlantirishlar; axe toza", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1, name: "Boshlangʻich holat" });
    expect(await screen.findByText("Soat")).toBeTruthy();
    expect(screen.getByText("Sumka")).toBeTruthy();
    expect(norm(document.body.textContent)).toContain("Tushumning 25");
    expect(screen.getByText(/2 ta partiya boshlash sanasidan oldin/)).toBeTruthy();
    expect(screen.getByText("Boshlangʻich holat oʻrnatilmagan")).toBeTruthy();
    expect((screen.getByLabelText("Boshlash sanasi") as HTMLInputElement).value).toBe("2026-11-01");
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });

  it("narx kiritilgan qatorlar yuboriladi; javob keshga", async () => {
    const api = renderPage({ [PUT]: () => json(200, data({ start_on: "2026-11-01", coverage: "0.7700" })) });
    await screen.findByText("Soat");
    const prices = screen.getAllByLabelText(/Tannarx \/ dona/);
    fireEvent.change(prices[0]!, { target: { value: "12000" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash va qayta hisoblash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    expect(api.bodiesOf(PUT)[0]).toEqual({ start_on: "2026-11-01", rows: [{ item_id: "item-1", uzum_qty: 120, own_qty: 0, prices: [{ valid_from: null, unit_cost: "12000" }] }] });
    expect(await screen.findByText(/Saqlandi/)).toBeTruthy();
    await waitFor(() => expect(norm(document.body.textContent)).toContain("Tushumning 77"));
  });

  it("sana almashsa — shu sana uchun taklif so'raladi; o'chirish", async () => {
    const api = renderPage({
      [ROUTE]: [() => json(200, data({ start_on: "2026-10-01", as_of: "2026-10-01" })), () => json(200, data({ start_on: "2026-10-01", as_of: "2026-09-01", stock_source: "none" }))],
      [PUT]: () => json(200, data()),
    });
    await screen.findByText("Soat");
    fireEvent.change(screen.getByLabelText("Boshlash sanasi"), { target: { value: "2026-09-01" } });
    expect(await screen.findByText(/qoldigʻi saqlanmagan/)).toBeTruthy();
    expect(api.fetch.mock.calls.some(([r]) => (r as Request).url.includes("start=2026-09-01"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toEqual([{ start_on: null, rows: [] }]));
  });

  it("buxgalter faqat ko'radi", async () => {
    renderPage({}, "accountant");
    await screen.findByText("Soat");
    expect(screen.queryByRole("button", { name: "Saqlash va qayta hisoblash" })).toBeNull();
    expect((screen.getByLabelText("Boshlash sanasi") as HTMLInputElement).disabled).toBe(true);
  });
});
