import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, unwrap } from "./client";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("API mijozi", () => {
  it("CSRF sarlavhasi va cookie bilan so'raydi", async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(request.headers.get("X-Requested-With")).toBe("web");
      expect(request.credentials).toBe("include");
      expect(new URL(request.url).pathname).toBe("/api/v1/auth/me");
      return json(200, { user: { id: "u", phone: "+998", name: null, language: "uz-Latn" }, orgs: [] });
    });
    const api = createApi({ baseUrl: "http://test", fetch });
    const me = await unwrap(api.GET("/api/v1/auth/me"));
    expect(me.orgs).toEqual([]);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("problem+json → ApiError (code, detail, request id)", async () => {
    const api = createApi({
      baseUrl: "http://test",
      fetch: async () =>
        json(
          403,
          { type: "x", title: "Forbidden", status: 403, code: "forbidden", detail: "Ruxsat yo'q", request_id: "r1" },
          { "Content-Type": "application/problem+json" },
        ),
    });
    const error = await unwrap(api.GET("/api/v1/auth/me")).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "forbidden", detail: "Ruxsat yo'q", requestId: "r1" });
    expect((error as ApiError).retryable).toBe(false);
  });

  it("problem'siz javob va tarmoq xatosi", async () => {
    const html = createApi({
      baseUrl: "http://test",
      fetch: async () => new Response("<html>", { status: 502, headers: { "X-Request-ID": "r2" } }),
    });
    const bad = (await unwrap(html.GET("/api/v1/auth/me")).catch((e: unknown) => e)) as ApiError;
    expect([bad.status, bad.code, bad.requestId, bad.retryable]).toEqual([502, "http_502", "r2", true]);

    const offline = createApi({
      baseUrl: "http://test",
      fetch: async () => {
        throw new TypeError("Failed to fetch");
      },
    });
    const net = (await unwrap(offline.GET("/api/v1/auth/me")).catch((e: unknown) => e)) as ApiError;
    expect([net.status, net.code, net.retryable]).toEqual([0, "network", true]);
    expect(new ApiError(429, null).retryable).toBe(true);
  });

  it("204 — bo'sh javob xato emas", async () => {
    const api = createApi({ baseUrl: "http://test", fetch: async () => new Response(null, { status: 204 }) });
    await expect(unwrap(api.POST("/api/v1/auth/logout"))).resolves.toBeUndefined();
  });
});
