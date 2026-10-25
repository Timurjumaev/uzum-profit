// Server holati (03 §9): TanStack Query, staleTime 60 s. 4xx qayta so'ralmaydi (ruxsat yoki kiritish masalasi),
// tarmoq/5xx/429 — 2 marta. Sessiya tugasa (401) — kirish sahifasiga (`onUnauthorized`).
import { MutationCache, QueryCache, QueryClient, queryOptions } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "../lib/api/client";

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
