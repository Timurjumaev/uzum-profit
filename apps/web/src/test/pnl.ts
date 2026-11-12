// Namunaviy `/pnl` javobi (M5): tannarxsiz qism (qamrov 90%), kompensatsiya, o'z xarajati, kutilayotgan qism (F16,
// ADR-037) ikki do'konda. Zanjir: 7 500 000 − 750 000 (tannarxsiz) − 3 000 000 = 3 750 000 yalpi; − 400 000 + 100 000
// − 200 000 − 100 000 + 60 000 = 3 210 000 sof foyda = yakunlangan 3 020 000 + kutilayotgan 190 000 (kutilayotgan zanjiri:
// 900 000 − 300 000 − 360 000 = 240 000; − 48 000 + 12 000 − 24 000 − 12 000 + 22 000 = 190 000). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type Pnl = components["schemas"]["PnlOut"];
type Statement = components["schemas"]["StatementOut"];

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SHOP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export function pnlStatement(over: Partial<Statement> = {}): Statement {
  return {
    revenue: "10000000.00",
    commission: "2000000.00",
    logistics: "500000.00",
    payout: "7500000.00",
    cogs: "3000000.00",
    gross_profit: "3750000.00",
    uzum_expenses: { advertising: "400000.00", compensation: "-100000.00" },
    uzum_total: "300000.00",
    own_expenses: { ijara: "200000.00" },
    own_total: "200000.00",
    tax: "100000.00",
    expenses_deducted: "540000.00",
    net_profit: "3210000.00",
    coverage: "0.900000",
    margin: "0.356667",
    roi: "1.070000",
    units: 60,
    covered_units: 54,
    lines: 50,
    units_processing: 8,
    revenue_processing: "1200000.00",
    net_profit_done: "3020000.00",
    net_profit_processing: "190000.00",
    revenue_done: "8800000.00",
    units_done: 52,
    lines_processing: 6,
    logistics_estimated: "40000.00",
    logistics_estimated_units: 4,
    logistics_estimated_lines: 3,
    logistics_missing_lines: 0,
    uzum_estimated: {},
    idle_expenses: "0.00",
    uncovered: { lines: 4, revenue: "1000000.00", payout: "750000.00", expenses: "60000.00", share: "0.100000" },
    direct_total: "250000.00",
    allocated_total: "250000.00",
    uzum_allocated: { advertising: "50000.00" },
    own_allocated: { ijara: "200000.00" },
    uzum_direct: "250000.00",
    uzum_allocated_total: "50000.00",
    own_direct: "0.00",
    own_allocated_total: "200000.00",
    ...over,
  };
}

const row = (code: string, amount: string, processing: string, previous: string, change: string | null, share: string | null) => ({
  code,
  amount,
  done: (Number(amount) - Number(processing)).toFixed(2),
  processing,
  share_of_revenue: share,
  previous,
  diff: (Number(amount) - Number(previous)).toFixed(2),
  change,
  change_estimated: false,
});

type ExpectedPart = components["schemas"]["ExpectedOut"];

/** Kutilayotgan sof foyda (F16, ADR-037): 8 dona, 1 200 000 tushum, logistikaning 40 000 qismi taxminiy. */
export function expectedPart(over: Partial<ExpectedPart> = {}): ExpectedPart {
  return {
    units: 8,
    lines: 6,
    revenue: "1200000.00",
    commission: "240000.00",
    logistics: "60000.00",
    cogs: "360000.00",
    expenses: "50000.00",
    net_profit: "190000.00",
    uncovered_lines: 2,
    logistics_estimated: "40000.00",
    logistics_estimated_units: 4,
    logistics_missing_lines: 0,
    uzum_estimated: {},
    rate: "0.850000",
    ...over,
  };
}

export function pnlData(over: Partial<Pnl> = {}): Pnl {
  const statement = pnlStatement();
  return {
    meta: {
      period: { start: "2026-09-01", end: "2026-10-31", days: 61 },
      previous: { start: "2026-07-02", end: "2026-08-31", days: 61 },
      shops: null,
      freshness: { orders: new Date().toISOString(), expenses: new Date().toISOString() },
    },
    statement,
    previous: pnlStatement({ revenue: "8000000.00", net_profit: "2500000.00" }),
    rows: [
      row("revenue", "10000000.00", "1200000.00", "8000000.00", "0.250000", "1.000000"),
      row("commission", "-2000000.00", "-240000.00", "-1600000.00", "-0.250000", "-0.200000"),
      row("logistics", "-500000.00", "-60000.00", "-450000.00", "-0.111111", "-0.050000"),
      row("payout", "7500000.00", "900000.00", "5950000.00", "0.260504", "0.750000"),
      row("cogs", "-3000000.00", "-360000.00", "-2500000.00", "-0.200000", "-0.300000"),
      row("gross_profit", "3750000.00", "240000.00", "3450000.00", "0.086957", "0.375000"),
      row("uzum:advertising", "-400000.00", "-48000.00", "-300000.00", "-0.333333", "-0.040000"),
      row("uzum:compensation", "100000.00", "12000.00", "0.00", null, "0.010000"),
      row("own:ijara", "-200000.00", "-24000.00", "-200000.00", "0.000000", "-0.020000"),
      row("tax", "-100000.00", "-12000.00", "-80000.00", "-0.250000", "-0.010000"),
      row("uncovered_payout", "750000.00", "300000.00", "400000.00", "0.875000", "0.075000"),
      row("uncovered_expenses", "60000.00", "22000.00", "30000.00", "1.000000", "0.006000"),
      row("net_profit", "3210000.00", "190000.00", "2500000.00", "0.284000", "0.321000"),
    ],
    columns: [
      { key: "2026-09-01", statement: pnlStatement({ revenue: "4000000.00", net_profit: "1210000.00", net_profit_done: "1210000.00", net_profit_processing: "0.00" }), title: null, shop_id: null },
      { key: "2026-10-01", statement: pnlStatement({ revenue: "6000000.00", net_profit: "2000000.00", net_profit_done: "1810000.00", net_profit_processing: "190000.00" }), title: null, shop_id: null },
    ],
    expected: expectedPart(),
    expected_shops: [
      { shop_id: SHOP_A, ...expectedPart({ units: 6, lines: 4, revenue: "900000.00", net_profit: "160000.00", rate: "0.870000" }) },
      { shop_id: SHOP_B, ...expectedPart({ units: 2, lines: 2, revenue: "300000.00", net_profit: "30000.00", uncovered_lines: 0, logistics_estimated: "0.00", logistics_estimated_units: 0, rate: null }) },
    ],
    recalculated: 0,
    untaxed_regimes: [],
    tax_missing_bhm: false,
    ...over,
  };
}

/** SKU ko'rinishi ustunlari: zararli, foydali, bog'lanmagan va taqsimlanmagan (tartib aralash — UI saralaydi). */
export function skuColumns(): Pnl["columns"] {
  return [
    { key: null, statement: pnlStatement({ revenue: "0.00", net_profit: "-150000.00" }), title: null, shop_id: null },
    { key: "s-loss", statement: pnlStatement({ net_profit: "-90000.00", margin: "-0.050000" }), title: "Kamar L", shop_id: SHOP_B },
    { key: "unlinked", statement: pnlStatement({ net_profit: "0.00" }), title: null, shop_id: null },
    { key: "s-top", statement: pnlStatement({ net_profit: "3450000.00" }), title: "Sumka qora M", shop_id: SHOP_A },
  ];
}
