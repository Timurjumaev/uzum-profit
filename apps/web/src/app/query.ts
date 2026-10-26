// Server holati (03 §9): TanStack Query, staleTime 60 s. 4xx qayta so'ralmaydi (ruxsat yoki kiritish masalasi),
// tarmoq/5xx/429 — 2 marta. Sessiya tugasa (401) — kirish sahifasiga (`onUnauthorized`).
import { MutationCache, QueryCache, QueryClient, queryOptions } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "../lib/api/client";
import type { WaiverIn } from "../lib/api/types";

export const STALE_MS = 60_000;
export const MAX_RETRIES = 2;

export function shouldRetry(failures: number, error: unknown): boolean {
  if (failures >= MAX_RETRIES) return false;
  return error instanceof ApiError ? error.retryable : true;
}

export function makeQueryClient(onUnauthorized: () => void = () => {}): QueryClient {
  const unauthorized = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: unauthorized }),
    mutationCache: new MutationCache({ onError: unauthorized }),
    defaultOptions: {
      queries: { staleTime: STALE_MS, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
}

/** Joriy foydalanuvchi va tashkilotlari; 401 — kirmagan. */
export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
  retry: (failures, error) => !(error instanceof ApiError && error.status === 401) && shouldRetry(failures, error),
});

/** Tanlangan tashkilot — hozircha birinchisi (tashkilotni almashtirish — M1, B3.7). */
export function currentOrg(me: { orgs: Array<{ id: string; name: string; role: string }> }) {
  return me.orgs[0] ?? null;
}

/** Tashkilot do'konlari (topbar filtri, M2 nomi va rangi bilan). */
export const shopsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "shops"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/shops", { params: { path: { org_id: orgId } } })),
  });

export const SYNC_POLL_MS = 60_000;

/** Sinxron holati (M3): "Yangilandi: ..." ko'rsatkichi va uzilish banneri; har daqiqa yangilanadi. */
export const syncQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "sync"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/sync", { params: { path: { org_id: orgId } } })),
    refetchInterval: SYNC_POLL_MS,
  });

/** "Hozir yangilash" (M3): ustuvor navbat, tashkilot bo'yicha daqiqada bir marta. */
export const refreshSync = (orgId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/sync/refresh", { params: { path: { org_id: orgId } } }));

export const logout = () => unwrap(api.POST("/api/v1/auth/logout"));

// --- Kirish, tashkilot, ulanish (B3.7) ----------------------------------------------------------------------------

/** Kodni Telegram'ga yuborish (M1). `phone` — `+998XXXXXXXXX`. */
export const requestOtp = (phone: string) => unwrap(api.POST("/api/v1/auth/otp", { body: { phone } }));

/** Kod bilan kirish: sessiya cookie'si o'rnatiladi, foydalanuvchi va tashkilotlari qaytadi. */
export const loginWithCode = (phone: string, code: string) => unwrap(api.POST("/api/v1/auth/login", { body: { phone, code } }));

export const updateProfile = (body: { name?: string | null; language?: "uz-Latn" | "uz-Cyrl" | "ru" | null }) =>
  unwrap(api.PATCH("/api/v1/auth/me", { body }));

export const acceptInvite = (token: string) => unwrap(api.POST("/api/v1/invites/accept", { body: { token } }));

export const createOrg = (body: { name: string; inn?: string | null }) => unwrap(api.POST("/api/v1/orgs", { body }));

/** Uzum kaliti: tekshiriladi va shifrlanadi; javobda kalit yo'q (faqat oxirgi 4 belgi). */
export const connectAccount = (orgId: string, token: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/accounts", { params: { path: { org_id: orgId } }, body: { token } }));

export const updateShop = (orgId: string, shopId: string, body: { active?: boolean; alias?: string | null; color?: string | null }) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/shops/{shop_id}", { params: { path: { org_id: orgId, shop_id: shopId } }, body }));

// --- Hisobotlar (B4): davr + do'konlar filtri bilan -----------------------------------------------------------------

/** Hisobot so'rovi parametrlari: `app/filters` dan (bo'sh `shops` — hamma do'kon). */
export type ReportParams = { shops: string[]; start: string; end: string };

const reportQuery = (p: ReportParams) => ({ start: p.start, end: p.end, shop: p.shops.length > 0 ? p.shops : undefined });

/** Bosh sahifa (M4): hisob varag'i, davr chizig'i, kunlik grafik, TOP/zarar SKU, ko'rsatkichlar, "Diqqat talab qiladi". */
export const dashboardQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "dashboard", p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/dashboard", { params: { path: { org_id: orgId }, query: reportQuery(p) } })),
  });

/** Foyda va zarar (M5): hisob varag'i (oldingi davr bilan), kesim ustunlari (`view`), F16, F40. */
export const pnlQuery = (orgId: string, p: ReportParams, view: "month" | "shop" | "sku") =>
  queryOptions({
    queryKey: ["orgs", orgId, "pnl", view, p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/pnl", { params: { path: { org_id: orgId }, query: { ...reportQuery(p), view } } })),
  });

// --- Uzum bonuslari (ADR-031) -------------------------------------------------------------------------------------

/** Bonus davrlari (faol va rad etilgan) va tanlash mumkin bo'lgan bepul xarajat turlari. */
export const feeWaiversQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "fee-waivers"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/fee-waivers", { params: { path: { org_id: orgId } } })),
  });

export const createWaiver = (orgId: string, body: WaiverIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/fee-waivers", { params: { path: { org_id: orgId } }, body }));

export const deleteWaiver = (orgId: string, waiverId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/fee-waivers/{waiver_id}", { params: { path: { org_id: orgId, waiver_id: waiverId } } }));

/** Drill-down: Yakunlangan sotuv qatorlari (P&L qatorlari yig'indisi shulardan), kursor bilan sahifalanadi. */
export const salesPage = (orgId: string, p: ReportParams, cursor: string | null) =>
  unwrap(
    api.GET("/api/v1/orgs/{org_id}/sales", {
      params: { path: { org_id: orgId }, query: { ...reportQuery(p), group: "completed", limit: 50, cursor } },
    }),
  );

/** Drill-down: bitta Uzum toifasi xarajatlari va o'z xarajatlari (`own_items` — hamma toifa, mijozda saralanadi). */
export const expensesPage = (orgId: string, p: ReportParams, category: string | null, cursor: string | null) =>
  unwrap(
    api.GET("/api/v1/orgs/{org_id}/expenses", {
      params: { path: { org_id: orgId }, query: { ...reportQuery(p), category, limit: 50, cursor } },
    }),
  );
