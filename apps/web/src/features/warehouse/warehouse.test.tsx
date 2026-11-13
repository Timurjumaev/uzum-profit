// Omborim (TM5, ADR-061 §7): SKU bo'yicha qoldiq va qiymat, boshqa SKU'ga o'tkazish (manba partiya, maqsad SKU, dona),
// o'tkazmani bekor qilish, keyin topilgan brak (writeoff, sabab defect), omborchi — summasiz. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import type { PickerRow, WarehouseRow } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { json, ME, ME_ROUTE, mockApi, SKU_PICKER_ROUTE, type Routes } from "../../test/api";

const ORG = ME.orgs[0]!.id;
const WAREHOUSE_ROUTE = `GET /api/v1/orgs/${ORG}/warehouse`;
const TRANSFER_ROUTE = `POST /api/v1/orgs/${ORG}/warehouse/transfer`;
const MOVE_ROUTE = `POST /api/v1/orgs/${ORG}/stock-moves`;
const SKU_A = "a1111111-1111-4111-8111-111111111111";
const SKU_B = "a2222222-2222-4222-8222-222222222222";
const ITEM = "e1111111-1111-4111-8111-111111111111";
const LINE = "f1111111-1111-4111-8111-111111111111";
const MOVED = "f2222222-2222-4222-8222-222222222222";

const row = (over: Partial<WarehouseRow> = {}): WarehouseRow => ({
  key: `sku:${SKU_A}`,
  sku_id: SKU_A,
  item_id: ITEM,
  shop_id: "b1111111-1111-4111-8111-111111111111",
  shop: "byDurii",
  title: "Mashina-Qizil",
  product_title: "Mashina",
  barcode: "4780000000001",
  qty: 70,
  reserved: 0,
  dispatched: 0,
  unit_cost: "10000.00",
  value: "700000.00",
  sources: [{ line_id: LINE, purchase_id: "p1", purchase_title: "Oktabr partiyasi", counted_on: "2026-10-20", qty: 70, unit_cost: "10000.00" }],
  transfers_in: [],
  ...over,
});
const WAREHOUSE = {
  items: [row(), row({ key: `sku:${SKU_B}`, sku_id: SKU_B, shop: "EL-ONE", title: "Mashina EL", qty: 30, value: "300000.00", sources: [], transfers_in: [{ line_id: MOVED, purchase_id: "p1", qty: 30, from_sku_id: SKU_A, from_name: "Mashina-Qizil" }] })],
  amounts: true,
  total_qty: 100,
  total_value: "1000000.00",
};
const picker = (over: Partial<PickerRow>): PickerRow => ({ sku_id: null, item_id: null, item_name: null, shop_id: "b1", shop: "byDurii", product_title: null, title: null, article: null, image_url: null, stock: null, sold: null, status: null, ...over });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [WAREHOUSE_ROUTE]: () => json(200, WAREHOUSE),
    [SKU_PICKER_ROUTE]: () => json(200, { rows: [picker({ sku_id: SKU_A, title: "Mashina-Qizil", product_title: "Mashina" }), picker({ sku_id: SKU_B, title: "Mashina EL", product_title: "Mashina", shop: "EL-ONE" })], truncated: false }),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/warehouse"] }), "uz-Latn")} />);
  return api;
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("Omborim", () => {
  it("SKU bo'yicha qoldiq, qiymat, o'tkazilgan qator; boshqa SKU'ga o'tkazish", async () => {
    const api = await renderAt({ [TRANSFER_ROUTE]: () => json(201, WAREHOUSE) });
    const table = await screen.findByRole("table", { name: "Omborim" });
    const rows = within(table).getAllByRole("row");
    expect(rows[1]!.textContent).toContain("Mashina-Qizil");
    expect(rows[2]!.textContent).toContain("30 dona — Mashina-Qizil dan oʻtkazilgan");
    expect(screen.getByText(/Jami 100 dona/)).toBeTruthy();
    // Manbasi yo'q qatorda o'tkazish o'chiq.
    expect((screen.getAllByRole("button", { name: "Boshqa SKUʼga: Mashina EL" })[0] as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getAllByRole("button", { name: "Boshqa SKUʼga: Mashina-Qizil" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Boshqa SKUʼga oʻtkazish" });
    const box = await within(dialog).findByRole("combobox", { name: "Qaysi SKUʼga" });
    await waitFor(() => expect((box as HTMLInputElement).disabled).toBe(false));
    fireEvent.focus(box);
    const options = within(await screen.findByRole("listbox")).getAllByRole("option");
    expect(options).toHaveLength(1); // o'sha SKU ro'yxatda yo'q
    fireEvent.mouseDown(options[0]!);
    const save = within(dialog).getByRole("button", { name: "Oʻtkazish" }) as HTMLButtonElement;
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "71" } });
    expect(save.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Dona/), { target: { value: "20" } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, TRANSFER_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, TRANSFER_ROUTE)[0]).toEqual({ source_line_id: LINE, to_sku_id: SKU_B, qty: 20 });
    expect(await screen.findByText("Oʻtkazildi")).toBeTruthy();
  });

  it("o'tkazmani bekor qilish — DELETE", async () => {
    const del = `DELETE /api/v1/orgs/${ORG}/warehouse/transfers/${MOVED}`;
    const api = await renderAt({ [del]: () => new Response(null, { status: 204 }) });
    fireEvent.click(await screen.findByRole("button", { name: "Oʻtkazmani bekor qilish: Mashina EL, 30 dona" }));
    await waitFor(() => expect(api.count(del)).toBe(1));
    expect(await screen.findByText("Oʻtkazma bekor qilindi")).toBeTruthy();
  });

  it("keyin topilgan brak: writeoff, sabab defect, SKU va partiya bilan", async () => {
    const api = await renderAt({ [MOVE_ROUTE]: () => json(201, {}) });
    fireEvent.click((await screen.findAllByRole("button", { name: "Brak: Mashina-Qizil" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Keyin topilgan brak" });
    fireEvent.change(within(dialog).getByLabelText(/^Brak dona/), { target: { value: "2" } });
    fireEvent.change(within(dialog).getByLabelText(/^Izoh/), { target: { value: " Qadoq yirtiq " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Hisobdan chiqarish" }));
    await waitFor(() => expect(bodiesOf(api, MOVE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, MOVE_ROUTE)[0]).toEqual({ item_id: ITEM, kind: "writeoff", reason: "defect", qty: 2, day: todayTashkent(), note: "Qadoq yirtiq", sku_id: SKU_A, purchase_line_id: LINE });
    expect(await screen.findByText("Brak hisobdan chiqarildi")).toBeTruthy();
  });

  it("omborchi — summasiz; buxgalter — amallarsiz; bo'sh holat", async () => {
    await renderAt({ [WAREHOUSE_ROUTE]: () => json(200, { ...WAREHOUSE, amounts: false, total_value: null, items: WAREHOUSE.items.map((r) => ({ ...r, unit_cost: null, value: null })) }) }, "warehouse");
    const table = await screen.findByRole("table", { name: "Omborim" });
    expect(within(table).queryByRole("columnheader", { name: "Qiymati" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "Brak: Mashina-Qizil" }).length).toBeGreaterThan(0);
    cleanup();
    await renderAt({}, "accountant");
    await screen.findByRole("table", { name: "Omborim" });
    expect(screen.queryByRole("button", { name: /^Brak/ })).toBeNull();
    cleanup();
    await renderAt({ [WAREHOUSE_ROUTE]: () => json(200, { items: [], amounts: true, total_qty: 0, total_value: "0.00" }) });
    expect(await screen.findByText("Omborimda tovar yoʻq")).toBeTruthy();
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt();
    await screen.findByRole("table", { name: "Omborim" });
    const results = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});
