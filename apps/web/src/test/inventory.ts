// Namunaviy `/inventory` va `/stock-moves` javoblari (M10, B4.7). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type S = components["schemas"];

export const SKU_CRIT = "d1111111-1111-4111-8111-111111111111";
export const SKU_DEAD = "d2222222-2222-4222-8222-222222222222";
export const ITEM_CRIT = "e1111111-1111-4111-8111-111111111111";
export const ITEM_DEAD = "e2222222-2222-4222-8222-222222222222";
export const MOVE_1 = "f1111111-1111-4111-8111-111111111111";

const LOCATIONS: S["LocationsOut"] = { fbo: 8, fbs: 2, defected: 1, pending: 0, china: 20, road: 30, own: 15 };

/** Kritik SKU: tezlik 2/kun, zaxira 5 kun, muddat 32 kun — buyurtma kechikkan, tavsiya 90 dona. */
export function stockRow(over: Partial<S["StockRowOut"]> = {}): S["StockRowOut"] {
  return {
    sku_id: SKU_CRIT,
    shop_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    item_id: ITEM_CRIT,
    product_id: null,
    title: "Oʻyinchoq mashina qizil",
    product_title: "Mashina",
    qty_active: 8,
    qty_fbs: 2,
    qty_defected: 1,
    qty_pending: 0,
    stock: 10,
    in_transit: 50,
    locations: LOCATIONS,
    velocity: { value: "2.0000", base: "2.0000", return_rate: "0.0000", trend_ratio: "1.0000", trend_factor: "1.00", days_counted: 14 },
    days_of_stock: "5.0",
    lead_time: { total: "32", stages: { prep: "8", china: "2", cargo: "13", receive: "7", handover: "2" }, learned: ["cargo", "china", "handover", "prep", "receive"] },
    status: "critical",
    product_status: null,
    abc: "A",
    xyz: "X",
    liquidity: null,
    last_sale_on: "2026-10-30",
    order_by: { day: "2026-10-31", overdue: true },
    reorder: { qty: 90, raw: "89.00", budget: [{ amount: "90000.00", currency: "CNY" }, { amount: "9000000.00", currency: "UZS" }] },
    unit_cost: "100000.00",
    stock_value: "1000000.00",
    ...over,
  };
}

/** Harakatsiz SKU: sotuv yo'q, qoldiq bor, muddat noma'lum — buyurtma sanasi va tavsiya yo'q. */
export function deadRow(over: Partial<S["StockRowOut"]> = {}): S["StockRowOut"] {
  return stockRow({
    sku_id: SKU_DEAD,
    item_id: ITEM_DEAD,
    title: "Chiroq LED",
    product_title: null,
    qty_active: 40,
    qty_fbs: 0,
    qty_defected: 0,
    stock: 40,
    in_transit: 0,
    locations: { fbo: 40, fbs: 0, defected: 0, pending: 0, china: 0, road: 0, own: 0 },
    velocity: { value: "0.0000", base: "0.0000", return_rate: "0.0000", trend_ratio: null, trend_factor: "1.00", days_counted: 14 },
    days_of_stock: null,
    lead_time: null,
    status: "dead",
    abc: "C",
    xyz: null,
    liquidity: "slow",
    last_sale_on: "2026-07-20",
    order_by: null,
    reorder: null,
    unit_cost: "50000.00",
    stock_value: "2000000.00",
    ...over,
  });
}

export function inventoryData(over: Partial<S["InventoryOut"]> = {}): S["InventoryOut"] {
  const meta = { period: { start: "2026-10-31", end: "2026-10-31" }, shops: [], freshness: {}, uses_stale_data: false, compare: null } as unknown as S["Meta"];
  return {
    meta,
    as_of: "2026-10-31",
    items: [stockRow(), deadRow()],
    total: 2,
    next_cursor: null,
    totals: {
      frozen_money: { china: "2400000.00", road: "3600000.00", own: "1500000.00", fbo: "800000.00", fbs: "200000.00", defected: "100000.00" },
      frozen_total: "8600000.00",
      average_days_to_sell: "12.5",
      uncosted: 0,
      units: { china: 20, road: 30, own: 15, fbo: 48, fbs: 2, defected: 1 },
      statuses: { critical: 1, dead: 1 },
    },
    ...over,
  };
}

export function move(over: Partial<S["StockMoveOut"]> = {}): S["StockMoveOut"] {
  return { id: MOVE_1, item_id: ITEM_CRIT, kind: "writeoff", qty: 3, day: "2026-10-20", note: "Qabulda brak", purchase_line_id: null, created_at: "2026-10-20T05:00:00Z", ...over };
}
