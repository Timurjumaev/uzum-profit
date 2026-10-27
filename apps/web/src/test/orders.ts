// Namunaviy `/sales` va `/orders/analysis` javoblari (M7, B4.4). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type Sales = components["schemas"]["SalesOut"];
type Sale = components["schemas"]["SaleOut"];
type Analysis = components["schemas"]["OrdersAnalysisOut"];

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SKU_X = "51111111-1111-4111-8111-111111111111";

const meta = {
  period: { start: "2026-10-01", end: "2026-10-20", days: 20 },
  previous: null,
  shops: null,
  freshness: { orders: "2026-10-26T10:00:00Z" },
};

export function sale(over: Partial<Sale> = {}): Sale {
  return {
    id: "s1",
    shop_id: SHOP_A,
    sku_id: SKU_X,
    sku_title: "Oʻyinchoq mashina",
    order_id: 100,
    external_id: 1,
    ordered_at: "2026-10-02T07:00:00Z",
    day: "2026-10-02",
    status: "TO_WITHDRAW",
    group: "completed",
    amount: 2,
    amount_returns: 0,
    return_cause: null,
    sell_price: "200000.00",
    revenue: "400000.00",
    commission: "80000.00",
    logistics: "10000.00",
    payout: "310000.00",
    cogs: "200000.00",
    gross_profit: "110000.00",
    cost_flags: [],
    recalculated_at: null,
    previous_cogs: null,
    waiver_id: null,
    ...over,
  };
}

export function salesData(over: Partial<Sales> = {}): Sales {
  return {
    meta,
    items: [
      sale(),
      sale({ id: "s2", day: "2026-10-03", status: "CANCELED", group: "canceled", amount: 0, amount_returns: 1, cogs: null, gross_profit: null, payout: "0.00", revenue: "0.00" }),
      sale({ id: "s3", day: "2026-10-04", sku_id: null, sku_title: null, cogs: null, gross_profit: null, cost_flags: ["no_item"], waiver_id: "w1" }),
      sale({ id: "s4", day: "2026-10-05", status: "PROCESSING", group: "processing", cost_flags: ["estimated"] }),
    ],
    next_cursor: null,
    summary: { units: 13, canceled: 5, returns: 3, cancel_share: "0.277778", return_share: "0.187500" },
    ...over,
  };
}

export function analysisData(over: Partial<Analysis> = {}): Analysis {
  return {
    meta,
    summary: {
      units: 13,
      canceled: 5,
      returns: 3,
      cancel_share: "0.277778",
      return_share: "0.187500",
      canceled_after_issue: 2,
      after_issue_share: "0.400000",
      return_storage_cost: "49000.00",
    },
    daily: [
      { day: "2026-10-02", units: 7, canceled: 0, returns: 1, cancel_share: "0.000000", return_share: "0.125000" },
      { day: "2026-10-04", units: 1, canceled: 1, returns: 1, cancel_share: "0.500000", return_share: "0.500000" },
    ],
    by_sku: [
      { sku_id: SKU_X, title: "Oʻyinchoq mashina", units: 6, canceled: 2, returns: 2, cancel_share: "0.250000", return_share: "0.250000" },
      { sku_id: null, title: null, units: 1, canceled: 0, returns: 1, cancel_share: "0.000000", return_share: "0.500000" },
    ],
    return_causes: [
      { cause: "Sifat yomon", units: 2 },
      { cause: null, units: 1 },
    ],
    cancel_causes: [{ cause: "Mijoz fikrini oʻzgartirdi", units: 2 }],
    ...over,
  };
}
