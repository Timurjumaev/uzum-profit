// Namunaviy `/calculator` va `/calculator/defaults` javoblari (B5.9). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type Defaults = components["schemas"]["CalculatorDefaultsOut"];
type Calc = components["schemas"]["CalculatorOut"];

export const cargoSuggestion = (over: Partial<components["schemas"]["CargoSuggestionOut"]> = {}): components["schemas"]["CargoSuggestionOut"] => ({
  purchases: 0,
  usd_per_kg: null,
  weighed: 0,
  uzs_per_unit: null,
  since: null,
  ...over,
});

export function calculatorDefaults(over: Partial<Defaults> = {}): Defaults {
  return {
    rates: { cny: "1750.00", usd: "12600.00", day: "2026-11-19", source: "cbu" },
    tax_pct: "4.0000",
    tax_on_payout: false,
    tariff: { valid_from: "2026-06-01", base_fee: "5250.00", per_liter: "250.00", max_fee: "50000.00", no_dims_fee: "50000.00" },
    ...over,
  };
}

export function calculatorResult(over: Partial<Calc> = {}): Calc {
  return {
    rates: { cny: "1750.00", usd: "12600.00", day: "2026-11-19", source: "cbu" },
    landed: { goods: "17500.00", china: "1750.00", cargo: "15120.00", extra: "1000.00", unit_cost: "35370.00", cargo_basis: "weight" },
    logistics: { fee: "5250.00", liters: 1, source: "dims" },
    tax_pct: "4.0000",
    unit: {
      price: "90000.00",
      fixed: "40620.00",
      share_pct: "19.00",
      commission: "13500.00",
      tax: "3600.00",
      ads: "0.00",
      profit: "32280.00",
      margin: "0.358667",
      roi: "0.912639",
      breakeven: "50148.00",
      target_price: null,
    },
    ...over,
  };
}
