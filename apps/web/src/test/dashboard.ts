// Namunaviy `/dashboard` javobi (M4): vitest va Playwright e2e umumiy fixture'i — vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SHOP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

type Dashboard = components["schemas"]["DashboardOut"];

const row = (code: string, amount: string, previous: string, change: string | null, share: string | null = null) => ({
  code,
  amount,
  share_of_revenue: share,
  previous,
  diff: String(Number(amount) - Number(previous)),
  change,
});

const statement = (): Dashboard["statement"] => ({
  revenue: "186420000.00",
  commission: "37284000.00",
  logistics: "9135750.00",
  payout: "140000250.00",
  cogs: "78112050.00",
  gross_profit: "61888200.00",
  uzum_expenses: { advertising: "6000000.00", storage: "5631000.00" },
  own_expenses: {},
  tax: "1864200.00",
  expenses_deducted: "13495200.00",
  net_profit: "48393000.00",
  coverage: "1.000000",
  margin: "0.259400",
  roi: "0.619000",
  units: 1240,
  covered_units: 1240,
  lines: 1180,
  uncovered: { lines: 0, revenue: "0.00", payout: "0.00", expenses: "0.00", share: "0.000000" },
  direct_total: "0.00",
  allocated_total: "0.00",
  uzum_allocated: {},
  own_allocated: {},
  uzum_total: "11631000.00",
  own_total: "0.00",
  uzum_direct: "11631000.00",
  uzum_allocated_total: "0.00",
  own_direct: "0.00",
  own_allocated_total: "0.00",
});

/** Namunaviy `/dashboard` javobi: 2026-10-01..2026-10-26, hammasi tannarxli (override bilan o'zgartiriladi). */
export function dashboardData(over: Partial<Dashboard> = {}, ago: (minutes: number) => string = minutesAgo): Dashboard {
  return {
    meta: {
      period: { start: "2026-10-01", end: "2026-10-26", days: 26 },
      previous: { start: "2026-09-05", end: "2026-09-30", days: 26 },
      shops: null,
      freshness: { orders: ago(3), expenses: ago(25), products: ago(40), snapshot: ago(90) },
    },
    statement: statement(),
    rows: [
      row("revenue", "186420000.00", "165000000.00", "0.129818", "1.000000"),
      row("commission", "-37284000.00", "-33000000.00", "-0.129818", "0.200000"),
      row("logistics", "-9135750.00", "-9800000.00", "0.067781", "0.049000"),
      row("payout", "140000250.00", "122200000.00", "0.145670", "0.751000"),
      row("cogs", "-78112050.00", "-70000000.00", "-0.115887", "0.419000"),
      row("gross_profit", "61888200.00", "52200000.00", "0.185595", "0.332000"),
      row("uzum:advertising", "-6000000.00", "-5000000.00", "-0.200000", "0.032000"),
      row("uzum:storage", "-5631000.00", "-5700000.00", "0.012105", "0.030000"),
      row("tax", "-1864200.00", "-1650000.00", "-0.129818", "0.010000"),
      row("net_profit", "48393000.00", "43012000.00", "0.124274", "0.259000"),
    ],
    periods: [
      { key: "today", period: { start: "2026-10-26", end: "2026-10-26", days: 1 }, revenue: "5200000.00", net_profit: "1300000.00", units: 38 },
      { key: "yesterday", period: { start: "2026-10-25", end: "2026-10-25", days: 1 }, revenue: "7100000.00", net_profit: "1810000.00", units: 52 },
      { key: "this_month", period: { start: "2026-10-01", end: "2026-10-26", days: 26 }, revenue: "186420000.00", net_profit: "48393000.00", units: 1240 },
      { key: "last_month", period: { start: "2026-09-01", end: "2026-09-30", days: 30 }, revenue: "190000000.00", net_profit: "47000000.00", units: 1300 },
    ],
    forecast: { revenue: "216000000.00", net_profit: "56000000.00", units: "1437.00" },
    daily: [
      { day: "2026-10-24", revenue: "6000000.00", net_profit: "1500000.00", units: 44 },
      { day: "2026-10-25", revenue: "7100000.00", net_profit: "1810000.00", units: 52 },
      { day: "2026-10-26", revenue: "5200000.00", net_profit: "1300000.00", units: 38 },
    ],
    top: [
      { sku_id: "d1", shop_id: SHOP_A, title: "Sumka qora M", product_title: "Sumka", units: 120, revenue: "30000000.00", net_profit: "9000000.00", margin: "0.300000" },
      { sku_id: "d2", shop_id: SHOP_A, title: null, product_title: "Hamyon", units: 80, revenue: "12000000.00", net_profit: "3000000.00", margin: "0.250000" },
    ],
    bottom: [{ sku_id: "d3", shop_id: SHOP_B, title: "Kamar L", product_title: "Kamar", units: 9, revenue: "900000.00", net_profit: "-250000.00", margin: "-0.277000" }],
    kpis: {
      margin: "0.259400",
      uncovered_share: "0.000000",
      roi: "0.619000",
      cancel_share: "0.040000",
      return_share: "0.021000",
      drr: "0.032200",
      expected_profit: { amount: "4100000.00", rate: "0.870000", raw: "4713000.00", uncovered_lines: 0 },
      frozen_money: "92000000.00",
      in_transit_value: "31000000.00",
      average_days_to_sell: "41.50",
    },
    waivers: [],
    attention: { uncosted_lines: 0, uncosted_revenue: "0.00", loss_skus: 1, stock_critical: 2, stock_high: 3, recalculated: 0 },
    ...over,
  };
}
