// Namunaviy `/purchases` javoblari (M9, B4.6). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type S = components["schemas"];

export const PURCHASE_1 = "91111111-1111-4111-8111-111111111111";
export const PURCHASE_2 = "92222222-2222-4222-8222-222222222222";
export const LINE_1 = "a1111111-1111-4111-8111-111111111111";
export const LINE_2 = "a2222222-2222-4222-8222-222222222222";
export const COMP_GOODS = "c1111111-1111-4111-8111-111111111111";
export const ITEM_1 = "e1111111-1111-4111-8111-111111111111";

const STAGES: S["Stage"][] = ["ordered", "paid", "cn_warehouse", "shipped", "arrived", "received", "sent_to_uzum", "closed"];

/** Partiya yo'li: `current` gacha o'tilgan, keyingilari kutilmoqda. */
export function timeline(current: S["Stage"], dates: Partial<Record<S["Stage"], string>>, extra: Partial<S["StageOut"]> = {}): S["StageOut"][] {
  const index = STAGES.indexOf(current);
  return STAGES.map((stage, i) => ({
    stage,
    state: current === "closed" || i < index ? "done" : i === index ? "current" : "upcoming",
    on: dates[stage] ?? null,
    days: i === index && current !== "closed" ? 11 : null,
    expected: null,
    delayed: false,
    ...(i === index ? extra : {}),
  }));
}

export function purchaseRow(over: Partial<S["PurchaseOut"]> = {}): S["PurchaseOut"] {
  const dates = { ordered: "2026-10-02", paid: "2026-10-03", cn_warehouse: "2026-10-09", shipped: "2026-10-12" };
  return {
    id: PURCHASE_1,
    title: "Oktabr partiyasi",
    stage: "shipped",
    supplier_id: null,
    supplier_name: "Yiwu Toys",
    carrier_id: null,
    carrier_name: "Cargo Express",
    dates: { ordered: dates.ordered, paid: dates.paid, cn_warehouse: dates.cn_warehouse, shipped: dates.shipped, arrived: null, received: null, sent_to_uzum: null, closed: null },
    timeline: timeline("shipped", dates, { expected: "2026-10-28" }),
    line_count: 2,
    items: ["Mashina", "Yangi oʻyinchoq"],
    units_ordered: 150,
    units_received: null,
    total: "4664000.00",
    unit_cost: "31093.33",
    flags: ["cargo_missing", "not_received"],
    error: null,
    note: null,
    created_at: "2026-10-02T05:00:00Z",
    ...over,
  };
}

export function line(over: Partial<S["LineOut"]> = {}): S["LineOut"] {
  return {
    id: LINE_1,
    item_id: ITEM_1,
    item_name: "Mashina",
    item_image: null,
    temp_name: null,
    url: null,
    image_url: null,
    variant: null,
    ordered_qty: 100,
    received_qty: 98,
    shortage: 2,
    unit_price: "10.0000",
    currency: "CNY",
    unit_weight: "0.5000",
    unit_volume: null,
    flags: ["cbu_rate"],
    cost: { total: "1764000.00", unit_cost: "18000.00", breakdown: { goods: "1764000.00" } },
    ...over,
  };
}

export function component(over: Partial<S["ComponentOut"]> = {}): S["ComponentOut"] {
  return {
    id: COMP_GOODS,
    kind: "goods",
    amount: "1480.0000",
    currency: "CNY",
    paid_on: "2026-10-03",
    rate_mode: "cbu",
    rate: null,
    charged_amount: null,
    charged_currency: null,
    allocation: "value",
    lines: null,
    shares: {},
    applied_rate: "1800.000000",
    rate_day: "2026-10-03",
    amount_uzs: "2664000.00",
    error: null,
    ...over,
  };
}

export function purchaseDetail(over: Partial<S["PurchaseDetailOut"]> = {}): S["PurchaseDetailOut"] {
  return {
    purchase: purchaseRow(),
    amounts: true,
    lines: [
      line(),
      line({
        id: LINE_2,
        item_id: null,
        item_name: null,
        temp_name: "Yangi oʻyinchoq",
        url: "https://detail.1688.com/offer/1.html",
        variant: "qizil × M",
        ordered_qty: 50,
        received_qty: null,
        shortage: 0,
        unit_price: null,
        currency: null,
        unit_weight: "1.5000",
        flags: ["cargo_missing", "not_received"],
        cost: { total: "900000.00", unit_cost: "18000.00", breakdown: { goods: "900000.00" } },
      }),
    ],
    components: [component()],
    by_kind: { goods: "2664000.00" },
    recalc_pending: false,
    ...over,
  };
}
