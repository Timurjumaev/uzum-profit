// Namunaviy `/skus`, `/skus/{id}` va `/unit-calc` javoblari (M6, B4.3). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";
import { pnlStatement } from "./pnl";

type Skus = components["schemas"]["SkusOut"];
type Row = components["schemas"]["SkuRowOut"];
type Detail = components["schemas"]["SkuDetailOut"];
type Calc = components["schemas"]["UnitCalcOut"];

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SKU_1 = "51111111-1111-4111-8111-111111111111";
export const SKU_2 = "52222222-2222-4222-8222-222222222222";
export const ITEM_1 = "61111111-1111-4111-8111-111111111111";

const meta = {
  period: { start: "2026-09-01", end: "2026-10-31", days: 61 },
  previous: null,
  shops: null,
  freshness: { orders: "2026-10-26T10:00:00Z", expenses: "2026-10-26T10:00:00Z", products: "2026-10-26T10:00:00Z", snapshot: "2026-10-26T10:00:00Z" },
};

export function skuRow(over: Partial<Row> = {}): Row {
  return {
    sku_id: SKU_1,
    shop_id: SHOP_A,
    item_id: ITEM_1,
    product_id: null,
    title: "Oʻyinchoq mashina qizil",
    product_title: "Oʻyinchoq mashina",
    article: "ART-1",
    barcode: "4780001",
    image_url: null,
    price: "200000.00",
    units: 6,
    revenue: "1200000.00",
    avg_price: "200000.00",
    commission_share: "0.200000",
    logistics_per_unit: "5000.00",
    cogs_per_unit: "100000.00",
    ads_per_unit: "3333.33",
    acos: "0.016667",
    profit_per_unit: "40000.00",
    normative_profit_per_unit: "40000.00",
    saved_per_unit: null,
    normative_state: "none",
    net_profit: "240000.00",
    expenses_direct: "20000.00",
    expenses_allocated: "10000.00",
    margin: "0.200000",
    uncovered_share: "0.000000",
    uncovered_lines: 0,
    roi: "0.400000",
    return_share: "0.142857",
    cancel_share: "0.142857",
    label: "profitable",
    stock: 85,
    days_of_stock: "42.0",
    abc: "A",
    rank: "A",
    status: "ACTIVE",
    ...over,
  };
}

export const SECOND = skuRow({
  sku_id: SKU_2,
  item_id: null,
  title: "Кружка белая",
  product_title: null,
  article: null,
  barcode: null,
  units: 1,
  revenue: "150000.00",
  avg_price: "150000.00",
  cogs_per_unit: null,
  profit_per_unit: null,
  normative_profit_per_unit: null,
  net_profit: "-5000.00",
  margin: null,
  roi: null,
  label: "no_data",
  abc: "C",
  stock: 0,
  days_of_stock: null,
  uncovered_lines: 1,
  uncovered_share: "1.000000",
});

export function skusData(over: Partial<Skus> = {}): Skus {
  return {
    meta,
    items: [skuRow(), SECOND],
    total: 2,
    next_cursor: null,
    unlinked: pnlStatement({ units: 1, lines: 1, revenue: "50000.00", net_profit: "0.00" }),
    unallocated: pnlStatement({ units: 0, lines: 0, revenue: "0.00", net_profit: "-12000.00" }),
    bonus: { waivers: [], unestimated_kinds: [] },
    ...over,
  };
}

export function skuDetail(over: Partial<Detail> = {}): Detail {
  return {
    meta,
    sku: skuRow(),
    statement: pnlStatement({ units: 6, covered_units: 6 }),
    uzum_url: "https://uzum.uz/ru/product/987654",
    history: [
      { day: "2026-10-01", units: 0, revenue: "0.00", net_profit: "0.00", profit_per_unit: null, price: "200000.00", commission_pct: "20.0000", stock: 10 },
      { day: "2026-10-02", units: 2, revenue: "400000.00", net_profit: "80000.00", profit_per_unit: "40000.00", price: "200000.00", commission_pct: "20.0000", stock: 8 },
    ],
    lots: [
      { id: "71111111-1111-4111-8111-111111111111", ready_on: "2026-09-01", qty: 100, unit_cost: "100000.000000", total: "10000000.00", flags: ["cbu_rate"] },
      { id: "72222222-2222-4222-8222-222222222222", ready_on: null, qty: 20, unit_cost: "120000.000000", total: "2400000.00", flags: [] },
    ],
    returns: [
      { cause: "Defekt", units: 3 },
      { cause: null, units: 1 },
    ],
    stock_detail: { active: 80, fbs: 5, defected: 2, pending: 0, in_transit: 20, status: null },
    linked: { item_id: ITEM_1, name: "Mashina", skus: [{ sku_id: SKU_1, shop_id: SHOP_A, title: "Oʻyinchoq mashina qizil" }, { sku_id: SKU_2, shop_id: SHOP_A, title: "Кружка белая" }] },
    bonus: { waivers: [], unestimated_kinds: [] },
    calc: {
      price: "200000.00",
      unit_cost: "100000.00",
      logistics: "5000.00",
      packaging: "0",
      commission_pct: "20.00",
      tax_pct: "4.00",
      ads_pct: "1.67",
      sources: { price: "period", unit_cost: "period", logistics: "last_paid", commission_pct: "period", tax_pct: "period", ads_pct: "period" },
    },
    ...over,
  };
}

export function unitCalc(over: Partial<Calc> = {}): Calc {
  return {
    price: "200000.00",
    fixed: "105000.00",
    share_pct: "25.67",
    commission: "40000.00",
    tax: "8000.00",
    ads: "3340.00",
    profit: "43660.00",
    margin: "0.218300",
    roi: "0.436600",
    breakeven: "141301.00",
    target_price: null,
    ...over,
  };
}
