// Namunaviy `/dashboard` javobi (M4): vitest va Playwright e2e umumiy fixture'i — vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SHOP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

type Dashboard = components["schemas"]["DashboardOut"];

// ADR-037: har qatorda yakunlangan va kutilayotgan qism (`processing`), yakunlangan = jami − kutilayotgan.
const row = (code: string, amount: string, processing: string, previous: string, change: string | null, share: string | null = null) => ({
  code,
  amount,
  done: (Number(amount) - Number(processing)).toFixed(2),
  processing,
  share_of_revenue: share,
  previous,
  diff: String(Number(amount) - Number(previous)),
  change,
  change_estimated: false,
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
  units_processing: 410,
  revenue_processing: "61000000.00",
  net_profit_done: "31508700.00",
  net_profit_processing: "16884300.00",
  revenue_done: "125420000.00",
  units_done: 830,
  lines_processing: 400,
  logistics_estimated: "1900000.00",
  logistics_estimated_units: 380,
  logistics_estimated_lines: 360,
  logistics_missing_lines: 0,
  uzum_estimated: {},
  idle_expenses: "0.00",
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
    expected: {
      units: 410,
      lines: 400,
      revenue: "61000000.00",
      commission: "12200000.00",
      logistics: "1900000.00",
      cogs: "25600000.00",
      expenses: "4415700.00",
      net_profit: "16884300.00",
      uncovered_lines: 0,
      logistics_estimated: "1900000.00",
      logistics_estimated_units: 380,
      logistics_missing_lines: 0,
      uzum_estimated: {},
      rate: "0.870000",
    },
    rows: [
      row("revenue", "186420000.00", "61000000.00", "165000000.00", "0.129818", "1.000000"),
      row("commission", "-37284000.00", "-12200000.00", "-33000000.00", "-0.129818", "0.200000"),
      row("logistics", "-9135750.00", "-1900000.00", "-9800000.00", "0.067781", "0.049000"),
      row("payout", "140000250.00", "46900000.00", "122200000.00", "0.145670", "0.751000"),
      row("cogs", "-78112050.00", "-25600000.00", "-70000000.00", "-0.115887", "0.419000"),
      row("gross_profit", "61888200.00", "21300000.00", "52200000.00", "0.185595", "0.332000"),
      row("uzum:advertising", "-6000000.00", "-1963200.00", "-5000000.00", "-0.200000", "0.032000"),
      row("uzum:storage", "-5631000.00", "-1842500.00", "-5700000.00", "0.012105", "0.030000"),
      row("tax", "-1864200.00", "-610000.00", "-1650000.00", "-0.129818", "0.010000"),
      row("net_profit", "48393000.00", "16884300.00", "43012000.00", "0.124274", "0.259000"),
    ],
    periods: [
      { key: "today", period: { start: "2026-10-26", end: "2026-10-26", days: 1 }, revenue: "5200000.00", net_profit: "1300000.00", net_profit_done: "0.00", net_profit_processing: "1300000.00", units: 38, units_processing: 38, revenue_processing: "5200000.00" },
      { key: "yesterday", period: { start: "2026-10-25", end: "2026-10-25", days: 1 }, revenue: "7100000.00", net_profit: "1810000.00", net_profit_done: "60000.00", net_profit_processing: "1750000.00", units: 52, units_processing: 50, revenue_processing: "6800000.00" },
      { key: "this_month", period: { start: "2026-10-01", end: "2026-10-26", days: 26 }, revenue: "186420000.00", net_profit: "48393000.00", net_profit_done: "31508700.00", net_profit_processing: "16884300.00", units: 1240, units_processing: 410, revenue_processing: "61000000.00" },
      { key: "last_month", period: { start: "2026-09-01", end: "2026-09-30", days: 30 }, revenue: "190000000.00", net_profit: "47000000.00", net_profit_done: "47000000.00", net_profit_processing: "0.00", units: 1300, units_processing: 0, revenue_processing: "0.00" },
    ],
    forecast: { revenue: "216000000.00", net_profit: "56000000.00", units: "1437.00", estimated: false },
    daily: [
      { day: "2026-10-24", revenue: "6000000.00", net_profit: "1500000.00", units: 44, revenue_done: "1000000.00", revenue_processing: "5000000.00", net_profit_done: "250000.00", net_profit_processing: "1250000.00" },
      { day: "2026-10-25", revenue: "7100000.00", net_profit: "1810000.00", units: 52, revenue_done: "300000.00", revenue_processing: "6800000.00", net_profit_done: "60000.00", net_profit_processing: "1750000.00" },
      { day: "2026-10-26", revenue: "5200000.00", net_profit: "1300000.00", units: 38, revenue_done: "0.00", revenue_processing: "5200000.00", net_profit_done: "0.00", net_profit_processing: "1300000.00" },
    ],
    top: [
      { sku_id: "d1", shop_id: SHOP_A, title: "Sumka qora M", product_title: "Sumka", units: 120, revenue: "30000000.00", net_profit: "9000000.00", margin: "0.300000" },
      { sku_id: "d2", shop_id: SHOP_A, title: null, product_title: "Hamyon", units: 80, revenue: "12000000.00", net_profit: "3000000.00", margin: "0.250000" },
    ],
    bottom: [{ sku_id: "d3", shop_id: SHOP_B, title: "Kamar L", product_title: "Kamar", units: 9, revenue: "900000.00", net_profit: "-250000.00", margin: "-0.277000" }],
    summary: summaryData(),
    kpis: {
      uncovered_share: "0.000000",
      frozen_money: "92000000.00",
      in_transit_value: "31000000.00",
      average_days_to_sell: "41.50",
    },
    attention: { uncosted_lines: 0, uncosted_revenue: "0.00", loss_skus: 1, stock_critical: 2, stock_high: 3, stock_ship: 0, recalculated: 0 },
    ...over,
  };
}

type Summary = Dashboard["summary"];
type SummaryCard = Summary["groups"][number]["cards"][number];

const POINTS = ["2026-10-24", "2026-10-25", "2026-10-26"];

function card(key: string, formula: string, unit: SummaryCard["unit"], value: string | null, previous: string | null, change: string | null, good: SummaryCard["good"], series: (string | null)[] = [value, value, value]): SummaryCard {
  return { key, formula, unit, value, previous, change, good, warn: false, series };
}

/** KPI sarhisob (ADR-043): 4 guruh, 24 kartochka. Yalpi = tushum + bekor + qaytarish (so'mda va donada). */
export function summaryData(over: Partial<Summary> = {}): Summary {
  return {
    bucket: "day",
    points: POINTS,
    groups: [
      {
        key: "orders",
        cards: [
          card("gross_revenue", "F44", "money", "215420000.00", "206000000.00", "0.045728", "up"),
          card("revenue", "F3", "money", "186420000.00", "190000000.00", "-0.018842", "up", ["6000000.00", "7100000.00", "5200000.00"]),
          card("units", "F3", "count", "1240", "1300", "-0.046154", "up"),
          card("orders", "F45", "count", "1610", "1580", "0.018987", "up"),
          card("orders_net", "F45", "count", "1102", "1150", "-0.041739", "up"),
          card("net_order_share", "F45", "ratio", "0.684472", "0.727848", "-0.043376", "up"),
        ],
      },
      {
        key: "uzum",
        cards: [
          card("uzum_costs", "F46", "money", "52300000.00", "50100000.00", "0.043912", "down"),
          card("uzum_costs_share", "F46", "ratio", "0.280549", "0.263684", "0.016865", "down"),
          card("after_uzum", "F47", "money", "134120000.00", "139900000.00", "-0.041315", "up"),
          card("drr", "F19", "ratio", "0.032200", "0.030000", "0.002200", "down"),
          card("net_profit", "F12", "money", "48393000.00", "43012000.00", "0.125105", "up"),
          card("margin", "F13", "ratio", "0.259400", "0.226400", "0.033000", "up"),
          card("roi", "F14", "ratio", "0.619000", "0.580000", "0.039000", "up"),
        ],
      },
      {
        key: "returns",
        cards: [
          card("return_units", "F18", "count", "61", "70", "-0.128571", "down"),
          card("return_revenue", "F18", "money", "9150000.00", "10500000.00", "-0.128571", "down"),
          card("return_share", "F18", "ratio", "0.046959", "0.051095", "-0.004136", "down"),
          card("return_revenue_share", "F18", "ratio", "0.046783", "0.052369", "-0.005586", "down"),
          card("cancel_units", "F17", "count", "290", "250", "0.160000", "down"),
          card("cancel_revenue", "F17", "money", "19850000.00", "5500000.00", "2.609091", "down"),
          card("cancel_share", "F17", "ratio", "0.181141", "0.155280", "0.025861", "down"),
          card("cancel_revenue_share", "F17", "ratio", "0.092146", "0.026699", "0.065447", "down"),
        ],
      },
      {
        key: "average",
        cards: [
          card("average_check", "F48", "money", "169165.15", "165217.39", "0.023895", "up"),
          card("average_price", "F48", "money", "150338.71", "146153.85", "0.028633", null),
          card("units_per_order", "F48", "number", "1.125227", "1.130435", "-0.004607", "up"),
        ],
      },
    ],
    // F49 (ADR-053): bo'laklar yig'indisi = yalpi summa; tannarxsiz qism 0 (yashiriladi).
    flow: [
      { key: "gross_revenue", formula: "F44", value: "215420000.00", share: "1.000000" },
      { key: "cancel_revenue", formula: "F17", value: "19850000.00", share: "0.092146" },
      { key: "return_revenue", formula: "F18", value: "9150000.00", share: "0.042475" },
      { key: "uzum_costs", formula: "F46", value: "52300000.00", share: "0.242782" },
      { key: "cogs", formula: "F7", value: "70000000.00", share: "0.324947" },
      { key: "own_expenses", formula: "F10", value: "9000000.00", share: "0.041779" },
      { key: "tax", formula: "F11", value: "6727000.00", share: "0.031227" },
      { key: "uncosted", formula: "F15", value: "0.00", share: "0.000000" },
      { key: "net_profit", formula: "F12", value: "48393000.00", share: "0.224645" },
    ],
    ...over,
  };
}
