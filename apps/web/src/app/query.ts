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
