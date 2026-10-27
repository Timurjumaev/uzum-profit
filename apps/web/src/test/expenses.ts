// Namunaviy `/expenses` javobi (M8, B4.5). Vitest'ga bog'liq emas.
import type { components } from "../lib/api/schema";

type Expenses = components["schemas"]["ExpensesOut"];
type Item = components["schemas"]["ExpenseOut"];
type Own = components["schemas"]["OwnExpenseOut"];

const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const OWN_1 = "71111111-1111-4111-8111-111111111111";
export const OWN_2 = "72222222-2222-4222-8222-222222222222";

const meta = {
  period: { start: "2026-10-01", end: "2026-10-20", days: 20 },
  previous: null,
  shops: null,
  freshness: { expenses: "2026-10-26T10:00:00Z" },
};

export function uzumItem(over: Partial<Item> = {}): Item {
  return {
    id: "e1",
    shop_id: SHOP_A,
    external_id: 1,
    created_on: "2026-10-06T07:00:00Z",
    day: "2026-10-06",
    code: "C000010",
    raw_code: "C000010",
    category: "fine",
    type: "OUTCOME",
    amount: "50000.00",
    name: "Jarima: kechikish",
    status: "CREATED",
    excluded: null,
    in_pnl: true,
    order_id: null,
    sale_item_id: null,
    ...over,
  };
}

export function ownItem(over: Partial<Own> = {}): Own {
  return {
    id: OWN_1,
    category: "ijara",
    scope: "org",
    shop_id: null,
    item_id: null,
    start_on: "2026-10-01",
    end_on: "2026-10-31",
    amount: "310000.00",
    in_period: "200000.00",
    recurrence: null,
    note: "Ofis",
    ...over,
  };
}

export function expensesData(over: Partial<Expenses> = {}): Expenses {
  return {
    meta,
    uzum: [
      { category: "advertising", amount: "200000.00" },
      { category: "fine", amount: "50000.00" },
      { category: "compensation", amount: "-10000.00" },
    ],
    uzum_total: "240000.00",
    by_month: [{ month: "2026-10-01", categories: { advertising: "200000.00", fine: "50000.00", compensation: "-10000.00" } }],
    fines: [uzumItem()],
    own: [{ category: "ijara", amount: "200000.00" }, { category: "internet", amount: "100000.00" }],
    own_total: "300000.00",
    own_items: [ownItem(), ownItem({ id: OWN_2, category: "internet", scope: "shop", shop_id: SHOP_A, start_on: "2026-10-05", end_on: "2026-10-05", amount: "100000.00", in_period: "100000.00", recurrence: "monthly", note: null })],
    items: [uzumItem(), uzumItem({ id: "e2", category: "advertising", amount: "200000.00", name: "Reklama", day: "2026-10-07" }), uzumItem({ id: "e3", category: "storage", amount: "9000.00", name: "Saqlash", in_pnl: false, excluded: "status" })],
    next_cursor: null,
    ...over,
  };
}
