// Namunaviy `/payouts/forecast` javobi (B5.7). Vitest'ga bog'liq emas (e2e ham ishlatadi).
import type { PayoutForecast } from "../lib/api/types";

export function payoutForecast(over: Partial<PayoutForecast> = {}): PayoutForecast {
  return {
    schedule: "biweekly",
    fee_pct: "0.0000",
    rules: { lag_days: 10, urgent_fee_pct: "2.5000", delay_workdays: 4 },
    available: "1200000.00",
    unknown_date: "450000.00",
    events: [
      { expected: "2026-12-07", latest: "2026-12-11", gross: "1200000.00", fee: "0.00", net: "1200000.00", estimated: false },
      { expected: "2026-12-21", latest: "2026-12-25", gross: "3100000.00", fee: "0.00", net: "3100000.00", estimated: true },
    ],
    ...over,
  };
}
