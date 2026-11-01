// Boshlang'ich holat (F41) testlari uchun namunaviy qator.
import type { Opening, OpeningRow } from "../lib/api/types";

export function openingRow(over: Partial<OpeningRow> = {}): OpeningRow {
  return {
    item_id: "item-1",
    sku_id: null,
    name: "Soat",
    skus: ["Soat-qora"],
    revenue: "1000000.00",
    uzum_suggested: 120,
    uzum_qty: null,
    own_qty: null,
    prices: [],
    last_lot_cost: null,
    lots_after: 0,
    lots_before: 0,
    ...over,
  };
}

/** Boshlang'ich holat javobi: bitta tovar va bitta tovarsiz SKU (oldingi partiyalari bilan). */
export function openingData(over: Partial<Opening> = {}): Opening {
  return {
    start_on: null,
    as_of: "2026-11-01",
    stock_source: "current",
    coverage: "0.2500",
    rows: [
      openingRow(),
      openingRow({ item_id: null, sku_id: "sku-9", name: "Sumka", skus: ["Sumka-1"], revenue: "300000.00", uzum_suggested: 7, lots_before: 2, last_lot_cost: "9000.000000" }),
    ],
    ...over,
  };
}
