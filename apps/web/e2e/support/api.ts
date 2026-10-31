// Soxta API (brauzerda marshrut darajasida): holatli — kirish, tashkilot yaratish, kalit ulash, do'kon tahrirlash
// haqiqiydagidek ishlaydi, shuning uchun e2e butun foydalanuvchi yo'lini o'tadi. Vaqt qotirilgan (`NOW`): "3 daqiqa oldin"
// va "Shu oy" skrinshotlarda barqaror. So'rovlar `requests` da — kalit/kod to'g'ri yuborilganini tekshirish uchun.
import type { Page, Route } from "@playwright/test";

import { dashboardData } from "../../src/test/dashboard";
import { inventoryData } from "../../src/test/inventory";
import { pnlData, skuColumns, waiver } from "../../src/test/pnl";
import { PURCHASE_1, purchaseDetail, purchaseRow } from "../../src/test/purchases";

/** Qotirilgan vaqt (Toshkent). */
export const NOW = new Date("2026-10-26T14:00:00+05:00");
export const ago = (minutes: number) => new Date(NOW.getTime() - minutes * 60_000).toISOString();

export const ORG_ID = "11111111-1111-4111-8111-111111111111";
export const SHOP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SHOP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
export const PHONE = "+998901234567";
export const GOOD_CODE = "123456";
export const GOOD_KEY = "uzum-test-key-1234567890";

type Json = Record<string, unknown>;
type Shop = {
  id: string;
  account_id: string;
  external_id: number;
  name: string;
  alias: string | null;
  color: string | null;
  active: boolean;
  history_status: string | null;
  first_sale_on: string | null;
};
type Kind = {
  kind: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  status: string | null;
  mode: string | null;
  started_at: string | null;
  finished_at: string | null;
  fetched: number | null;
  written: number | null;
  total: number | null;
  error: string | null;
  http_status: number | null;
};

export const kind = (over: Partial<Kind> & { kind: string }): Kind => ({
  last_success_at: ago(3),
  last_attempt_at: ago(3),
  status: "ok",
  mode: "incremental",
  started_at: null,
  finished_at: null,
  fetched: null,
  written: null,
  total: null,
  error: null,
  http_status: null,
  ...over,
});

export type User = { id: string; phone: string; name: string | null; language: string };
export const USER: User = { id: "u1", phone: PHONE, name: "Temur", language: "uz-Latn" };
export type Org = { id: string; name: string; role: string };
export const ORG: Org = { id: ORG_ID, name: "byDurii", role: "owner" };

/** Yangi foydalanuvchi: ismi ham, tashkiloti ham yo'q. */
export const NEW_USER = { user: { ...USER, name: null }, orgs: [] as Org[] };

export const SHOPS: Shop[] = [
  { id: SHOP_A, account_id: "c", external_id: 106121, name: "byDurii", alias: "Durii", color: "#2A78D6", active: true, history_status: "2020-01-01", first_sale_on: "2025-03-14" },
  { id: SHOP_B, account_id: "c", external_id: 135204, name: "EL-ONE", alias: null, color: "#EB6834", active: true, history_status: "2020-01-01", first_sale_on: "2025-09-02" },
];

/** Sog'lom sinxron holati. */
export function healthySync(shops: Shop[] = SHOPS) {
  return {
    healthy: true,
    outage: { active: false, since: null, paused_until: null, recovered_from: null, recovered_at: null },
    accounts: [{ id: "acc-1", status: "active", quota_remaining: 98_500, checked_at: ago(7) }],
    shops: shops.map((s) => ({
      id: s.id,
      account_id: s.account_id,
      name: s.name,
      alias: s.alias,
      active: s.active,
      history_status: s.history_status,
      first_sale_on: s.first_sale_on,
      healthy: true,
      errors_24h: 0,
      kinds: [
        kind({ kind: "orders", fetched: 2465, written: 2465, total: 2465 }),
        kind({ kind: "expenses", last_success_at: ago(25), fetched: 203, written: 203, total: 203 }),
        kind({ kind: "products", last_success_at: ago(40), fetched: 412 }),
      ],
    })),
    freshness: { orders: ago(3), expenses: ago(25), products: ago(40), returns: null },
  };
}

/** Drill-down namunasi: bir sahifa yakunlangan sotuvlar (kursorsiz). */
const SALES = {
  meta: dashboardData({}, ago).meta,
  items: [
    ["s1", "2026-10-25", "Sumka qora M", 2, "200000.00", "40000.00", "10000.00", "150000.00", "80000.00"],
    ["s2", "2026-10-24", "Hamyon", 1, "120000.00", "24000.00", "9000.00", "87000.00", "50000.00"],
  ].map(([id, day, title, amount, revenue, commission, logistics, payout, cogs]) => ({
    id,
    shop_id: SHOP_A,
    sku_id: "d1",
    sku_title: title,
    order_id: 1,
    external_id: 1,
    ordered_at: `${day}T10:00:00Z`,
    day,
    status: "TO_WITHDRAW",
    group: "completed",
    amount,
    amount_returns: 0,
    return_cause: null,
    sell_price: "100000.00",
    revenue,
    commission,
    logistics,
    payout,
    cogs,
    gross_profit: "70000.00",
    cost_flags: [],
    recalculated_at: null,
    previous_cogs: null,
  })),
  next_cursor: null,
  summary: { units: 3, canceled: 0, returns: 0, cancel_share: null, return_share: null },
};

export type ApiState = {
  /** Kirgan foydalanuvchi (`null` — sessiya yo'q). */
  me: { user: User; orgs: Org[] } | null;
  /** Kirishdan keyin qaytadigan tashkilotlar (yangi foydalanuvchi — bo'sh). */
  orgsOnLogin: Org[];
  shops: Shop[];
  sync: Json;
  /** Kalit ulangach qaytadigan do'konlar va tarix holati. */
  afterConnect: { shops: Shop[]; sync: Json };
  /** Tarixni yuklash sekin ketayotgandek ko'rsatish. */
  loadingHistory: boolean;
};

export type Request = { method: string; path: string; body: unknown };

const problem = (route: Route, status: number, code: string) =>
  route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "x", title: "x", status, code }),
  });

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export function loadingSync(shops: Shop[]) {
  const base = healthySync(shops);
  return {
    ...base,
    shops: base.shops.map((s, i) => ({
      ...s,
      history_status: null,
      kinds:
        i === 0
          ? [
              kind({ kind: "orders", status: "running", fetched: 1900, written: 1830, total: 2465, mode: "history" }),
              kind({ kind: "expenses", fetched: 203, written: 203, total: 203, mode: "history" }),
              kind({ kind: "products", status: "running", fetched: 40, mode: "history" }),
            ]
          : [kind({ kind: "orders", status: "running", fetched: 300, written: 250, total: 900, mode: "history" })],
    })),
  };
}

/** Marshrutlarni o'rnatadi va holat/so'rovlarga havola qaytaradi. `page.clock` shu yerda qotiriladi. */
const PNL_EXTRA = {
  waivers: [waiver()], // Uzum bonusi (ADR-031): banner, haqiqiy hisob o'zgarmaydi
  waiver_suggestions: [{ shop_id: SHOPS[1]!.id, start_on: "2026-10-05", end_on: "2026-10-06", kinds: ["sale_logistics"] }],
};

export async function mockApi(page: Page, init: Partial<ApiState> = {}) {
  const state: ApiState = {
    me: { user: { ...USER }, orgs: [ORG] },
    orgsOnLogin: [ORG],
    shops: SHOPS.map((s) => ({ ...s })),
    sync: healthySync(),
    afterConnect: { shops: [], sync: {} },
    loadingHistory: false,
    ...init,
  };
  const requests: Request[] = [];
  await page.clock.setFixedTime(NOW);

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();
    const text = request.postData();
    const body = text ? (JSON.parse(text) as Json) : null;
    requests.push({ method, path, body });
    const key = `${method} ${path}`;

    if (key === "GET /auth/me") return state.me ? json(route, 200, state.me) : problem(route, 401, "unauthorized");
    if (key === "POST /auth/otp") return json(route, 202, { phone: PHONE, expires_in: 300 });
    if (key === "POST /auth/login") {
      if (body?.code !== GOOD_CODE) return problem(route, 422, "otp_invalid");
      state.me = { user: { ...USER }, orgs: state.orgsOnLogin };
      return json(route, 200, { ...state.me, created: state.orgsOnLogin.length === 0 });
    }
    if (key === "PATCH /auth/me") {
      if (state.me && body?.language) state.me.user.language = String(body.language);
      return json(route, 200, state.me?.user ?? USER);
    }
    if (key === "POST /auth/logout") {
      state.me = null;
      return route.fulfill({ status: 204 });
    }
    if (key === "POST /orgs") {
      const org = { id: ORG_ID, name: String(body?.name), role: "owner" };
      state.me?.orgs.push(org);
      return json(route, 201, { ...org, inn: body?.inn ?? null, language: "uz-Latn", timezone: "Asia/Tashkent", cost_method: "fifo", permissions: [] });
    }
    if (key === `GET /orgs/${ORG_ID}/shops`) return json(route, 200, state.shops);
    if (key === `GET /orgs/${ORG_ID}/sync`) return json(route, 200, state.sync);
    if (key === `GET /orgs/${ORG_ID}/dashboard`) return json(route, 200, dashboardData({}, ago));
    if (key === `GET /orgs/${ORG_ID}/pnl`) {
      // Uzum bonusi davri bilan (haqiqiy hisob o'zgarmaydi); SKU kesimi — aralash tartibdagi ustunlar.
      const sku = url.searchParams.get("view") === "sku";
      return json(route, 200, pnlData({ ...PNL_EXTRA, ...(sku ? { columns: skuColumns() } : {}) }));
    }
    if (key === `GET /orgs/${ORG_ID}/fee-waivers`)
      return json(route, 200, { items: [waiver()], kinds: ["sale_logistics", "advertising", "storage", "return_storage"] });
    if (key === `GET /orgs/${ORG_ID}/sales`) return json(route, 200, SALES);
    if (key === `GET /orgs/${ORG_ID}/inventory`) return json(route, 200, inventoryData());
    if (key === `GET /orgs/${ORG_ID}/purchases`) return json(route, 200, { items: [purchaseRow()], amounts: true });
    if (key === `GET /orgs/${ORG_ID}/purchases/${PURCHASE_1}`) return json(route, 200, purchaseDetail());
    if (key === `GET /orgs/${ORG_ID}/suppliers` || key === `GET /orgs/${ORG_ID}/carriers`) return json(route, 200, []);
    if (key === `POST /orgs/${ORG_ID}/sync/refresh`) return json(route, 202, { queued: 3 });
    if (key === `POST /orgs/${ORG_ID}/accounts`) {
      if (body?.token !== GOOD_KEY) return problem(route, 422, "mp_token_invalid");
      state.shops = state.afterConnect.shops;
      state.sync = state.afterConnect.sync;
      return json(route, 201, { id: "acc-1", provider: "uzum", status: "active", key_hint: "…7890", checked_at: ago(0), quota_remaining: null, created_at: ago(0), shops: state.shops });
    }
    const shopPatch = path.match(new RegExp(`^/orgs/${ORG_ID}/shops/([^/]+)$`));
    if (method === "PATCH" && shopPatch) {
      const shop = state.shops.find((s) => s.id === shopPatch[1]);
      if (!shop) return problem(route, 404, "not_found");
      Object.assign(shop, body);
      return json(route, 200, shop);
    }
    return problem(route, 404, "not_found");
  });

  return {
    state,
    requests,
    /** Shu yo'lga ketgan so'rovlar tanasi (masalan, `bodies("POST", "/auth/login")`). */
    bodies: (method: string, path: string) => requests.filter((r) => r.method === method && r.path === path).map((r) => r.body),
  };
}

export type Api = Awaited<ReturnType<typeof mockApi>>;
