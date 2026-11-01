// Testlar uchun soxta API (fetch): marshrut → javob (yoki ketma-ket javoblar, oxirgisi takrorlanadi). Ro'yxatda yo'q
// so'rov — xato (test sezsin) va `unmocked` ga yoziladi. Namunaviy javoblar — `ME`, `SHOPS`, `syncStatus`.
import { vi } from "vitest";

import type { components } from "../lib/api/schema";
import { dashboardData } from "./dashboard";
import { pnlData } from "./pnl";

export { dashboardData, pnlData };

export const ORG_ID = "11111111-1111-4111-8111-111111111111";
export const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SHOP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export const ME = {
  user: { id: "u1", phone: "+998901234567", name: "Temur", language: "uz-Latn" },
  orgs: [{ id: ORG_ID, name: "byDurii", role: "owner" }],
};

export const SHOPS: components["schemas"]["ShopOut"][] = [
  shop(SHOP_A, "byDurii", { alias: "Durii", color: "#2a78d6", external: 106121, firstSale: "2025-03-14" }),
  shop(SHOP_B, "EL-ONE", { color: null, external: 135204, firstSale: "2025-09-02" }),
];

function shop(id: string, name: string, o: { alias?: string; color?: string | null; external: number; firstSale: string }) {
  return {
    id,
    account_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    external_id: o.external,
    name,
    alias: o.alias ?? null,
    color: o.color ?? null,
    active: true,
    history_status: "full",
    first_sale_on: o.firstSale,
  };
}

const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

export function syncStatus(over: Partial<components["schemas"]["SyncStatusOut"]> = {}): components["schemas"]["SyncStatusOut"] {
  return {
    healthy: true,
    outage: { active: false, since: null, paused_until: null, recovered_from: null, recovered_at: null },
    accounts: [],
    shops: [
      { id: SHOP_A, account_id: "c", name: "byDurii", alias: null, active: true, history_status: "full", first_sale_on: "2025-03-14", healthy: true, errors_24h: 0, kinds: [] },
      { id: SHOP_B, account_id: "c", name: "EL-ONE", alias: null, active: true, history_status: "full", first_sale_on: "2025-09-02", healthy: true, errors_24h: 0, kinds: [] },
    ],
    freshness: { orders: minutesAgo(3), expenses: minutesAgo(25), products: minutesAgo(40), returns: null },
    ...over,
  };
}

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export const problem = (status: number, code: string, extra: Record<string, unknown> = {}) =>
  json(status, { type: "x", title: "x", status, code, ...extra }, { "Content-Type": "application/problem+json" });

type Reply = (request: Request) => Response | Promise<Response>;
export type Routes = Record<string, Reply | Reply[]>;

export const ME_ROUTE = "GET /api/v1/auth/me";
export const SHOPS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/shops`;
export const SYNC_ROUTE = `GET /api/v1/orgs/${ORG_ID}/sync`;
export const DASHBOARD_ROUTE = `GET /api/v1/orgs/${ORG_ID}/dashboard`;
export const PNL_ROUTE = `GET /api/v1/orgs/${ORG_ID}/pnl`;
export const SKUS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/skus`;
export const skuRoute = (skuId: string) => `GET /api/v1/orgs/${ORG_ID}/skus/${skuId}`;
export const UNIT_CALC_ROUTE = `GET /api/v1/orgs/${ORG_ID}/unit-calc`;
export const ITEMS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/items`;
export const linkRoute = (skuId: string) => `PUT /api/v1/orgs/${ORG_ID}/skus/${skuId}/item`;
export const SALES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/sales`;
export const ORDERS_ANALYSIS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/orders/analysis`;
export const EXPENSES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/expenses`;
export const OWN_CATEGORIES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/own-expense-categories`;
export const OWN_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/own-expenses`;
export const ownRoute = (method: "PATCH" | "DELETE", id: string) => `${method} /api/v1/orgs/${ORG_ID}/own-expenses/${id}`;
export const PURCHASES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/purchases`;
export const PURCHASE_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/purchases`;
export const purchaseRoute = (method: "GET" | "PATCH" | "DELETE", id: string) => `${method} /api/v1/orgs/${ORG_ID}/purchases/${id}`;
export const purchaseSubRoute = (method: "POST" | "PATCH" | "DELETE", id: string, sub: string) => `${method} /api/v1/orgs/${ORG_ID}/purchases/${id}/${sub}`;
export const INVENTORY_ROUTE = `GET /api/v1/orgs/${ORG_ID}/inventory`;
export const STOCK_MOVE_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/stock-moves`;
export const stockMovesRoute = (itemId: string) => `GET /api/v1/orgs/${ORG_ID}/items/${itemId}/stock-moves`;
export const stockMoveDeleteRoute = (id: string) => `DELETE /api/v1/orgs/${ORG_ID}/stock-moves/${id}`;
export const SETTINGS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/settings`;
export const COST_METHOD_ROUTE = `PUT /api/v1/orgs/${ORG_ID}/settings/cost-method`;
export const INVENTORY_SETTINGS_ROUTE = `PUT /api/v1/orgs/${ORG_ID}/settings/inventory`;
export const TAX_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/tax-profiles`;
export const taxRoute = (method: "PATCH" | "DELETE", id: string) => `${method} /api/v1/orgs/${ORG_ID}/tax-profiles/${id}`;
export const PAYOUT_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/payout-schedules`;
export const payoutDeleteRoute = (id: string) => `DELETE /api/v1/orgs/${ORG_ID}/payout-schedules/${id}`;
export const SUPPLIERS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/suppliers`;
export const SUPPLIER_CREATE_ROUTE = `POST /api/v1/orgs/${ORG_ID}/suppliers`;
export const CARRIERS_ROUTE = `GET /api/v1/orgs/${ORG_ID}/carriers`;
export const REFRESH_ROUTE = `POST /api/v1/orgs/${ORG_ID}/sync/refresh`;
export const LOGOUT_ROUTE = "POST /api/v1/auth/logout";
export const OTP_ROUTE = "POST /api/v1/auth/otp";
export const LOGIN_ROUTE = "POST /api/v1/auth/login";
export const PROFILE_ROUTE = "PATCH /api/v1/auth/me";
export const ORGS_ROUTE = "POST /api/v1/orgs";
export const CONNECT_ROUTE = `POST /api/v1/orgs/${ORG_ID}/accounts`;
export const INVITE_ROUTE = "POST /api/v1/invites/accept";
export const shopRoute = (shopId: string) => `PATCH /api/v1/orgs/${ORG_ID}/shops/${shopId}`;

/** Standart: kirgan foydalanuvchi, ikki do'kon, sog'lom sinxron. `routes` ularni almashtiradi yoki to'ldiradi. */
export function mockApi(routes: Routes = {}) {
  const table: Routes = {
    [ME_ROUTE]: () => json(200, ME),
    [SHOPS_ROUTE]: () => json(200, SHOPS),
    [SYNC_ROUTE]: () => json(200, syncStatus()),
    [DASHBOARD_ROUTE]: () => json(200, dashboardData()),
    [PNL_ROUTE]: () => json(200, pnlData()),
    [REFRESH_ROUTE]: () => json(202, { queued: 3 }),
    [LOGOUT_ROUTE]: () => new Response(null, { status: 204 }),
    [PROFILE_ROUTE]: () => json(200, ME.user),
    ...routes,
  };
  const calls: string[] = [];
  const unmocked: string[] = [];
  /** So'rov tanalari (JSON) — kalit, kod va h.k. to'g'ri yuborilganini tekshirish uchun. */
  const bodies: Array<{ key: string; body: unknown }> = [];
  const fetch = vi.fn(async (request: Request) => {
    const key = `${request.method} ${new URL(request.url).pathname}`;
    calls.push(key);
    const text = request.method === "GET" ? "" : await request.clone().text();
    if (text) bodies.push({ key, body: JSON.parse(text) });
    const entry = table[key];
    if (!entry) {
      unmocked.push(key);
      throw new Error(`mockApi: ${key} ro'yxatda yo'q`);
    }
    const reply = Array.isArray(entry) ? (entry.length > 1 ? entry.shift()! : entry[0]) : entry;
    return reply(request);
  });
  vi.stubGlobal("fetch", fetch);
  return {
    fetch,
    calls,
    unmocked,
    bodies,
    count: (key: string) => calls.filter((c) => c === key).length,
    bodiesOf: (key: string) => bodies.filter((b) => b.key === key).map((b) => b.body),
  };
}
