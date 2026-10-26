// Namunaviy `/pnl` javobi (M5): tannarxsiz qism (qamrov 90%), kompensatsiya, o'z xarajati, F16 ikki do'konda.
// Zanjir: 7 500 000 − 750 000 (tannarxsiz) − 3 000 000 = 3 750 000 yalpi; − 400 000 + 100 000 − 200 000 − 100 000
// + 60 000 = 3 210 000 sof foyda. Vitest'ga bog'liq emas (e2e ham ishlatishi mumkin).
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

const row = (code: string, amount: string, previous: string, change: string | null, share: string | null) => ({
  code,
  amount,
  share_of_revenue: share,
  previous,
  diff: (Number(amount) - Number(previous)).toFixed(2),
  change,
});

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
      row("revenue", "10000000.00", "8000000.00", "0.250000", "1.000000"),
      row("commission", "-2000000.00", "-1600000.00", "-0.250000", "-0.200000"),
      row("logistics", "-500000.00", "-450000.00", "-0.111111", "-0.050000"),
      row("payout", "7500000.00", "5950000.00", "0.260504", "0.750000"),
      row("cogs", "-3000000.00", "-2500000.00", "-0.200000", "-0.300000"),
      row("gross_profit", "3750000.00", "3450000.00", "0.086957", "0.375000"),
      row("uzum:advertising", "-400000.00", "-300000.00", "-0.333333", "-0.040000"),
      row("uzum:compensation", "100000.00", "0.00", null, "0.010000"),
      row("own:ijara", "-200000.00", "-200000.00", "0.000000", "-0.020000"),
      row("tax", "-100000.00", "-80000.00", "-0.250000", "-0.010000"),
      row("uncovered_payout", "750000.00", "400000.00", "0.875000", "0.075000"),
      row("uncovered_expenses", "60000.00", "30000.00", "1.000000", "0.006000"),
      row("net_profit", "3210000.00", "2500000.00", "0.284000", "0.321000"),
    ],
    columns: [
      { key: "2026-09-01", statement: pnlStatement({ revenue: "4000000.00", net_profit: "1210000.00" }), title: null, shop_id: null },
      { key: "2026-10-01", statement: pnlStatement({ revenue: "6000000.00", net_profit: "2000000.00" }), title: null, shop_id: null },
    ],
    pending: { amount: "870000.00", rate: null, raw: "1000000.00", uncovered_lines: 2 },
    pending_shops: [
      { shop_id: SHOP_A, amount: "870000.00", rate: "0.870000", raw: "1000000.00", uncovered_lines: 2 },
      { shop_id: SHOP_B, amount: null, rate: null, raw: "300000.00", uncovered_lines: 0 },
    ],
    recalculated: 0,
    waivers: [],
    waiver_suggestions: [],
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

/** Uzum bonusi davri (ADR-031) — namunaviy yozuv. */
export function waiver(over: Partial<Pnl["waivers"][number]> = {}): Pnl["waivers"][number] {
  return {
    id: "w-1",
    shop_id: null,
    start_on: "2026-10-10",
    end_on: "2026-10-31",
    kinds: ["sale_logistics", "storage"],
    reason: "Uzum nosozligi uchun kompensatsiya",
    source: "manual",
    dismissed: false,
    created_at: "2026-10-26T10:00:00Z",
    ...over,
  };
}
