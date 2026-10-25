// API mijozi (03 §8, §9): openapi-fetch + generatsiya qilingan sxema. Xatolar RFC 9457 problem+json — `ApiError`
// (`code` bo'yicha matn i18n'da, B3.2). Kirish cookie orqali (HttpOnly), CSRF uchun `X-Requested-With` (03 §10).
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Problem = components["schemas"]["Problem"];

export const CSRF_HEADER = "X-Requested-With";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | null;
  readonly requestId: string | null;

  constructor(status: number, problem: Partial<Problem> | null, requestId: string | null = null) {
    const code = problem?.code ?? (status === 0 ? "network" : `http_${status}`);
    super(problem?.detail ?? problem?.title ?? code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = problem?.detail ?? null;
    this.requestId = problem?.request_id ?? requestId;
  }

  /** Server yoki tarmoq xatosi — qayta urinish mantiqli; 4xx — yo'q (foydalanuvchi yoki ruxsat masalasi). */
  get retryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }
}

const csrf: Middleware = {
  onRequest({ request }) {
    request.headers.set(CSRF_HEADER, "web");
    return request;
  },
};

export function createApi(
  options: { baseUrl?: string; fetch?: (request: Request) => Promise<Response> } = {},
) {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? globalThis.location?.origin ?? "",
    credentials: "include",
    // Chaqiruv paytidagi global fetch (testlar uni almashtira oladi).
    fetch: options.fetch ?? ((request) => globalThis.fetch(request)),
  });
  client.use(csrf);
  return client;
}

export const api = createApi();

type Result<T> = { data?: T; error?: unknown; response: Response };

/** openapi-fetch natijasi → ma'lumot yoki `ApiError`. Tarmoq xatosi (fetch rad etilsa) — `status` 0. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, null);
  }
  const { data, error, response } = result;
  if (!response.ok) {
    const problem = error && typeof error === "object" ? (error as Partial<Problem>) : null;
    throw new ApiError(response.status, problem, response.headers.get("X-Request-ID"));
  }
  return data as T; // 204 (chiqish, o'chirish) — `undefined`
}
