// Testlar uchun soxta API (fetch): marshrut → javob (yoki ketma-ket javoblar, oxirgisi takrorlanadi). Ro'yxatda yo'q
// so'rov — xato (test sezsin) va `unmocked` ga yoziladi. Namunaviy javoblar — `ME`, `SHOPS`, `syncStatus`.
import { vi } from "vitest";

import type { components } from "../lib/api/schema";
import { dashboardData } from "./dashboard";

export { dashboardData };

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
export const SALES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/sales`;
export const EXPENSES_ROUTE = `GET /api/v1/orgs/${ORG_ID}/expenses`;
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
