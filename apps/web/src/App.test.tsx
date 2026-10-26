import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "./App";
import { AppErrorBoundary, errorText } from "./app/errors";
import { createI18n } from "./lib/i18n";
import { I18nextProvider } from "react-i18next";
import { makeQueryClient, meQuery, shouldRetry, STALE_MS } from "./app/query";
import { loginSearch } from "./app/router";
import { ApiError } from "./lib/api/client";
import { json, ME, ME_ROUTE, mockApi, problem } from "./test/api";

/** `responses` — /auth/me ga ketma-ket javoblar (oxirgisi takrorlanadi). */
function serve(...responses: Array<() => Response>) {
  return mockApi({ [ME_ROUTE]: responses });
}

function renderAt(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const state = createAppState(history, "uz-Latn");
  render(<App state={state} />);
  return { history, state };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ilova karkasi (B3.1)", () => {
  it("kirgan foydalanuvchi — bosh sahifa, tashkilotlar bilan", async () => {
    const api = serve(() => json(200, ME));
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Uzum Profit" })).toBeTruthy();
    expect(await screen.findByText("byDurii")).toBeTruthy();
    expect(api.unmocked).toEqual([]);
  });

  it("kirmagan (401) — /login ga, qaytish manzili bilan", async () => {
    serve(() => problem(401, "unauthorized"));
    const { history } = renderAt("/status?x=1");
    expect(await screen.findByRole("heading", { name: "Kirish" })).toBeTruthy();
    expect(history.location.pathname).toBe("/login");
    expect(new URLSearchParams(history.location.search).get("redirect")).toBe("/status?x=1");
  });

  it("server xatosi — xato sahifasi, so'rov ID, qayta urinish", async () => {
    const api = serve(
      () => problem(503, "unavailable", { request_id: "req-42" }),
      () => problem(503, "unavailable", { request_id: "req-42" }),
      () => problem(503, "unavailable", { request_id: "req-42" }),
      () => json(200, ME),
    );
    renderAt("/");
    const alert = await screen.findByRole("alert", {}, { timeout: 5000 });
    expect(alert.textContent).toContain("Server javob bermadi");
    expect(alert.textContent).toContain("Soʻrov ID: req-42");
    expect(api.count(ME_ROUTE)).toBe(3); // 1 + 2 qayta urinish
    fireEvent.click(screen.getByRole("button", { name: "Qayta urinish" }));
    expect(await screen.findByText("byDurii")).toBeTruthy();
  });

  it("noma'lum manzil — 404 sahifasi", async () => {
    serve(() => json(200, ME));
    renderAt("/yoq-sahifa");
    expect(await screen.findByRole("heading", { name: "Sahifa topilmadi" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Bosh sahifaga qaytish" }).getAttribute("href")).toBe("/");
  });

  it("login: faqat ichki qaytish manzili", () => {
    expect(loginSearch({ redirect: "/pnl?x=1" })).toEqual({ redirect: "/pnl?x=1" });
    for (const bad of ["//evil.example", "/\\evil.example", "https://evil.example", 5]) {
      expect(loginSearch({ redirect: bad })).toEqual({});
    }
  });

  it("sessiya ish davomida tugasa — /login ga, kesh tozalanadi", async () => {
    serve(() => json(200, ME), () => problem(401, "unauthorized"));
    const { history, state } = renderAt("/status");
    expect(await screen.findByRole("heading", { name: "Maʼlumotlar holati" })).toBeTruthy();
    // Boshqa qurilmadan chiqildi — keyingi so'rov 401.
    await state.queryClient.refetchQueries({ queryKey: meQuery.queryKey }).catch(() => undefined);
    expect(await screen.findByRole("heading", { name: "Kirish" })).toBeTruthy();
    expect(history.location.pathname).toBe("/login");
    expect(new URLSearchParams(history.location.search).get("redirect")).toBe("/status");
    expect(state.queryClient.getQueryData(meQuery.queryKey)).toBeUndefined();
  });
});

describe("til (B3.2)", () => {
  it("ruscha va kirillcha karkas", async () => {
    serve(() => json(200, ME));
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/yoq"] }), "ru")} />);
    expect(await screen.findByRole("heading", { name: "Страница не найдена" })).toBeTruthy();
    cleanup();
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/yoq"] }), "uz-Cyrl")} />);
    expect(await screen.findByRole("heading", { name: "Саҳифа топилмади" })).toBeTruthy();
  });

  it("xato matni: avval API code, keyin HTTP holati", () => {
    const t = createI18n("uz-Latn").t;
    expect(errorText(new ApiError(400, { code: "otp_invalid" }), t)).toContain("Kod notoʻgʻri");
    expect(errorText(new ApiError(400, { code: "nomaʼlum" }), t)).toBe("Kutilmagan xatolik yuz berdi.");
    expect(errorText(new ApiError(404, { code: "not_found" }), t)).toBe("Maʼlumot topilmadi.");
    expect(errorText(new ApiError(403, { code: "forbidden" }), t)).toBe("Bu sahifaga ruxsatingiz yoʻq.");
    expect(errorText(new ApiError(429, null), t)).toContain("Soʻrovlar juda koʻp");
    expect(errorText(new Error("x"), t)).toBe("Kutilmagan xatolik yuz berdi.");
    const ruT = createI18n("ru").t;
    expect(errorText(new ApiError(0, null), ruT)).toContain("Нет подключения");
  });
});

describe("so'rov sozlamalari", () => {
  it("4xx qayta so'ralmaydi, tarmoq/5xx — 2 marta", () => {
    expect(STALE_MS).toBe(60_000);
    expect(shouldRetry(0, new ApiError(400, null))).toBe(false);
    expect(shouldRetry(0, new ApiError(401, null))).toBe(false);
    expect(shouldRetry(0, new ApiError(500, null))).toBe(true);
    expect(shouldRetry(1, new ApiError(0, null))).toBe(true);
    expect(shouldRetry(2, new ApiError(0, null))).toBe(false);
    expect(shouldRetry(0, new Error("x"))).toBe(true);
  });

  it("401 — onUnauthorized chaqiriladi", async () => {
    const onUnauthorized = vi.fn();
    const client = makeQueryClient(onUnauthorized);
    await client
      .fetchQuery({ queryKey: ["x"], queryFn: () => Promise.reject(new ApiError(401, null)), retry: false })
      .catch(() => undefined);
    expect(onUnauthorized).toHaveBeenCalledOnce();
    await client
      .fetchQuery({ queryKey: ["y"], queryFn: () => Promise.reject(new ApiError(403, null)), retry: false })
      .catch(() => undefined);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});

describe("AppErrorBoundary", () => {
  it("render xatosi — oq ekran emas, yangilash tugmasi", () => {
    const onError = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Broken(): never {
      throw new Error("buzildi");
    }
    render(
      <I18nextProvider i18n={createI18n("uz-Latn")}>
        <AppErrorBoundary onError={onError}>
          <Broken />
        </AppErrorBoundary>
      </I18nextProvider>,
    );
    expect(screen.getByRole("alert").textContent).toContain("Kutilmagan xatolik");
    expect(screen.getByRole("button", { name: "Sahifani yangilash" })).toBeTruthy();
    expect(onError).toHaveBeenCalledOnce();
  });
});
