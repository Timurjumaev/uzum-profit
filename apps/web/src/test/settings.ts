// Namunaviy `/settings` javobi (M16, B4.8). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type S = components["schemas"];

export const TAX_1 = "71111111-1111-4111-8111-111111111111";
export const TAX_2 = "72222222-2222-4222-8222-222222222222";
export const PAY_1 = "81111111-1111-4111-8111-111111111111";

export function settingsData(over: Partial<S["SettingsOut"]> = {}): S["SettingsOut"] {
  return {
    cost_method: "fifo",
    tax_profiles: [
      { id: TAX_2, valid_from: "2026-07-01", regime: "turnover", rate_pct: "4.000", base: "payout", vat_pct: "0.000", profit_pct: "0.000" },
      { id: TAX_1, valid_from: "2026-01-01", regime: "none", rate_pct: "0.000", base: "revenue", vat_pct: "0.000", profit_pct: "0.000" },
    ],
    tax_rates: [{ code: "turnover_ecommerce", rate_pct: "4.000", note: "e-tijorat" }],
    payout_schedules: [{ id: PAY_1, shop_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", kind: "weekly", valid_from: "2026-01-01" }],
    payout_terms: [
      { kind: "daily", days_of_month: null, fee_pct: "1.500" },
      { kind: "weekly", days_of_month: [7, 14, 21, 28], fee_pct: "1.000" },
      { kind: "biweekly", days_of_month: [7, 21], fee_pct: "0.000" },
      { kind: "monthly", days_of_month: [7], fee_pct: "0.000" },
    ],
    inventory: {
      stages: ["prep", "china", "cargo", "receive", "handover"],
      lead_days: null,
      cover_days: { A: 60, B: 30, C: 14 },
      cover_defaults: { A: 60, B: 30, C: 14 },
    },
    ...over,
  };
}
