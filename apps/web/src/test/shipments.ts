// Namunaviy `/shipments` javoblari (M9, B4.31, ADR-046). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";
import { component, LINE_1, LINE_2, PURCHASE_1, PURCHASE_2 } from "./purchases";

type S = components["schemas"];

export const SHIPMENT_1 = "b1111111-1111-4111-8111-111111111111";
export const SHIPMENT_COMP = "d1111111-1111-4111-8111-111111111111";

export function shipmentRow(over: Partial<S["ShipmentOut"]> = {}): S["ShipmentOut"] {
  return {
    id: SHIPMENT_1,
    title: "Presslangan oʻram",
    carrier_id: null,
    carrier_name: "Cargo Express",
    cn_warehouse_on: "2026-10-09",
    shipped_on: "2026-10-12",
    arrived_on: null,
    note: null,
    purchase_count: 2,
    units: 340,
    total: "2430000.00",
    created_at: "2026-10-05T10:00:00Z",
    ...over,
  };
}

export function shipmentDetail(over: Partial<S["ShipmentDetailOut"]> = {}): S["ShipmentDetailOut"] {
  return {
    shipment: shipmentRow(),
    amounts: true,
    purchases: [
      { id: PURCHASE_1, title: "A yetkazib beruvchi", supplier_name: "Yiwu Toys", stage: "shipped", state: "in_transit", line_count: 2, units: 140, share: "1682307.69", total: "1782307.69", unit_cost: "12730.77", error: null },
      { id: PURCHASE_2, title: "B yetkazib beruvchi", supplier_name: null, stage: "shipped", state: "in_transit", line_count: 1, units: 200, share: "747692.31", total: "747692.31", unit_cost: "3738.46", error: null },
    ],
    lines: [
      { id: LINE_1, purchase_id: PURCHASE_1, purchase_title: "A yetkazib beruvchi", name: "Mashina", qty: 100, unit_weight: "0.5000", unit_volume: null, share: "934615.38", share_per_unit: "9346.15", flags: [] },
      { id: LINE_2, purchase_id: PURCHASE_1, purchase_title: "A yetkazib beruvchi", name: "Qoʻgʻirchoq", qty: 40, unit_weight: "1.0000", unit_volume: null, share: "747692.31", share_per_unit: "18692.31", flags: ["base_fallback"] },
      { id: "a3333333-3333-4333-8333-333333333333", purchase_id: PURCHASE_2, purchase_title: "B yetkazib beruvchi", name: "Mashina", qty: 200, unit_weight: "0.2000", unit_volume: null, share: "747692.31", share_per_unit: "3738.46", flags: [] },
    ],
    components: [
      component({ id: SHIPMENT_COMP, kind: "cargo", amount: "2430000.0000", currency: "UZS", allocation: "weight", applied_rate: null, rate_day: null, rate_source: null, amount_uzs: "2430000.00", paid_on: null }),
    ],
    by_kind: { cargo: "2430000.00" },
    error: null,
    recalc_pending: false,
    ...over,
  };
}
