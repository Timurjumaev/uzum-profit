// Kalkulyator (M13, B5.9): kiritish → server hisobi (`/calculator`); majburiy maydonlar to'lmaguncha so'rov yo'q; soliq taklifi
// profildan; kurs manbasi; xatolar (kurs yo'q, noto'g'ri qiymat). Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { CALCULATOR_DEFAULTS_ROUTE, CALCULATOR_ROUTE, CARGO_SUGGESTION_ROUTE, SCENARIOS_ROUTE, SCENARIOS_SAVE_ROUTE, json, ME, ME_ROUTE, mockApi, problem, type Routes } from "../../test/api";
import { calculatorDefaults, calculatorResult, cargoSuggestion } from "../../test/calculator";
import { toInput, type Values } from "./CalculatorPage";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const m = (value: string) => norm(f.money(value));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderPage(routes: Routes = {}, lang: "uz-Latn" | "ru" = "uz-Latn") {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: lang } }),
    [CALCULATOR_DEFAULTS_ROUTE]: () => json(200, calculatorDefaults()),
    [CALCULATOR_ROUTE]: () => json(200, calculatorResult()),
    [CARGO_SUGGESTION_ROUTE]: () => json(200, cargoSuggestion()),
    [SCENARIOS_ROUTE]: () => json(200, []),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/calculator"] }), lang)} />);
  await screen.findByRole("heading", { level: 1, name: lang === "ru" ? "Калькулятор" : "Kalkulyator" });
  await screen.findByLabelText(lang === "ru" ? /^Цена 1688/ : /^1688 narxi/); // forma boshlang'ich qiymatlar kelgach chiziladi
  return api;
}

const calls = (api: ReturnType<typeof mockApi>) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === `/api/v1/orgs/${ME.orgs[0]!.id}/calculator`);

async function fill(label: RegExp | string, value: string) {
  fireEvent.change(await screen.findByLabelText(label), { target: { value } });
}

describe("kalkulyator", () => {
  it("ssenariy: saqlanganni ochish formani toʻldiradi; saqlash toʻldirilgan maydonlarni nom bilan yuboradi", async () => {
    const saved = [{ id: "s1", name: "Mashina", inputs: { price_cny: "10", qty: "50", price: "90000", commission_pct: "15" }, updated_at: "2026-11-20T10:00:00Z" }];
    const api = await renderPage({ [SCENARIOS_ROUTE]: () => json(200, saved), [SCENARIOS_SAVE_ROUTE]: () => json(201, saved[0]) });
    fireEvent.click(await screen.findByRole("button", { name: "Ochish" }));
    expect((screen.getByLabelText(/^1688 narxi/) as HTMLInputElement).value).toBe("10");
    expect((screen.getByLabelText(/^Dona soni/) as HTMLInputElement).value).toBe("50");
    expect((screen.getByLabelText("Ssenariy nomi") as HTMLInputElement).value).toBe("Mashina");
    const saveBtn = screen.getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    await waitFor(() => expect(saveBtn.disabled).toBe(false));
    fireEvent.click(saveBtn);
    await waitFor(() => expect(api.bodies.some((b) => b.key === SCENARIOS_SAVE_ROUTE)).toBe(true));
    const body = api.bodies.find((b) => b.key === SCENARIOS_SAVE_ROUTE)!.body as { name: string; inputs: Record<string, string> };
    expect(body.name).toBe("Mashina");
    expect(body.inputs.price_cny).toBe("10");
    expect("weight_kg" in body.inputs).toBe(false); // boʻsh maydon saqlanmaydi
  });


  it("kargo taklifi: oʻxshash xaridlar oʻrtachasi, tugma $/kg ni toʻldiradi; xarid yoʻq — taklif chiqmaydi", async () => {
    expect((await renderPage(), screen.queryByTestId("cargo-suggestion"))).toBeNull();
    cleanup();
    const api = await renderPage({ [CARGO_SUGGESTION_ROUTE]: () => json(200, cargoSuggestion({ purchases: 3, weighed: 2, usd_per_kg: "4.20", uzs_per_unit: "18000" })) });
    const box = await screen.findByTestId("cargo-suggestion");
    expect(norm(box.textContent!)).toContain("3 ta xarid");
    expect(norm(box.textContent!)).toContain("4,2 $/kg");
    fireEvent.click(screen.getByRole("button", { name: "Taklifni qoʻllash" }));
    expect((screen.getByLabelText(/^Kargo narxi \(\$\/kg\)/) as HTMLInputElement).value).toMatch(/4[,.]2/);
    expect(screen.queryByRole("button", { name: "Taklifni qoʻllash" })).toBeNull(); // qiymat taklifga teng
    expect(api.fetch).toBeTruthy();
  });


  it("majburiy maydonlar to'lmaguncha hisob so'ralmaydi; to'lgach natija server qiymatlari bilan", async () => {
    const api = await renderPage();
    expect(screen.getByText(/Hisoblash uchun 1688 narxi/)).toBeTruthy();
    expect(calls(api)).toHaveLength(0);
    await fill(/^1688 narxi/, "10");
    await fill(/^Moʻljallangan sotuv narxi/, "90000");
    await fill(/^Uzum komissiyasi/, "15");
    await waitFor(() => expect(calls(api).length).toBeGreaterThan(0));
    await waitFor(() => expect(norm(screen.getByTestId("calc-profit").textContent!)).toBe(m("32280.00")));
    expect(norm(screen.getByTestId("calc-unit-cost").textContent!)).toBe(m("35370.00"));
    expect(norm(screen.getByTestId("calc-logistics").textContent!)).toContain(m("5250.00"));
    expect(norm(screen.getByTestId("calc-logistics").textContent!)).toContain("1 l"); // F37: o'lchamdan
    expect(norm(screen.getByTestId("calc-breakeven").textContent!)).toBe(m("50148.00"));
    const q = calls(api).at(-1)!.searchParams;
    expect([q.get("price_cny"), q.get("price"), q.get("commission_pct"), q.get("qty")]).toEqual(["10", "90000", "15", "100"]);
    expect(q.get("tax_pct")).toBe("4.0000"); // soliq profilidan taklif
    expect(q.has("length_cm")).toBe(false); // o'lcham to'liq emas — yuborilmaydi
    expect(screen.getByText(/Oʻlchamsiz|vazn boʻyicha/)).toBeTruthy();
  });

  it("kurs manbasi va sanasi ko'rsatiladi; qo'lda kurs so'rovga yoziladi; kurs yo'q — izoh", async () => {
    const api = await renderPage();
    expect(screen.getAllByText(/Markaziy bank: 1 750 soʻm \(/).length).toBeGreaterThan(0);
    await fill(/^1688 narxi/, "10");
    await fill(/^Moʻljallangan sotuv narxi/, "90000");
    await fill(/^Uzum komissiyasi/, "15");
    await fill(/^CNY kursi/, "2000");
    await waitFor(() => expect(calls(api).some((u) => u.searchParams.get("cny_rate") === "2000")).toBe(true));
    cleanup();
    const none = calculatorDefaults({ rates: { cny: null, usd: null, day: null, source: null } });
    await renderPage({ [CALCULATOR_DEFAULTS_ROUTE]: () => json(200, none) });
    expect(screen.getAllByText("Kurs topilmadi — qoʻlda kiriting").length).toBe(2);
  });

  it("422: kurs yo'q — qo'lda kiriting; boshqa qiymat — maydonlarni tekshiring", async () => {
    await renderPage({ [CALCULATOR_ROUTE]: () => problem(422, "fx_rate_missing") });
    await fill(/^1688 narxi/, "10");
    await fill(/^Moʻljallangan sotuv narxi/, "90000");
    await fill(/^Uzum komissiyasi/, "15");
    expect((await screen.findByRole("alert")).textContent).toContain("CNY kursi topilmadi");
    cleanup();
    await renderPage({ [CALCULATOR_ROUTE]: () => problem(422, "validation_error") });
    await fill(/^1688 narxi/, "10");
    await fill(/^Moʻljallangan sotuv narxi/, "90000");
    await fill(/^Uzum komissiyasi/, "15");
    expect((await screen.findByRole("alert")).textContent).toContain("Qiymatlardan biri notoʻgʻri");
  });

  it("soliq profili yo'q — izoh; ulush ≥ 100% — ogohlantirish; maqsadli marja narxi", async () => {
    await renderPage({
      [CALCULATOR_DEFAULTS_ROUTE]: () => json(200, calculatorDefaults({ tax_pct: null })),
      [CALCULATOR_ROUTE]: () => json(200, calculatorResult({ unit: { ...calculatorResult().unit, share_pct: "105.00", breakeven: null, target_price: "99000.00" } })),
    });
    expect(screen.getByText("Soliq profili kiritilmagan — 0 olinadi")).toBeTruthy();
    await fill(/^1688 narxi/, "10");
    await fill(/^Moʻljallangan sotuv narxi/, "90000");
    await fill(/^Uzum komissiyasi/, "15");
    await fill(/^Maqsadli marja/, "20");
    expect(await screen.findByText(/yigʻindisi 105% — hech qanday narx foyda bermaydi/)).toBeTruthy();
    expect(norm(screen.getByTestId("calc-target").textContent!)).toBe(m("99000.00"));
    expect(screen.getByTestId("calc-breakeven").textContent).toBe("Narx yoʻq");
  });

  it("ruscha sahifa; menyuda 'Kalkulyator' bandi", async () => {
    await renderPage({}, "ru");
    expect(screen.getByRole("link", { name: "Калькулятор" })).toBeTruthy();
    expect(screen.getByText("Курс CNY (вручную)")).toBeTruthy();
  });

  it("toInput: majburiy maydon yo'q — null; o'lcham faqat uchalasi bo'lsa; bo'sh ixtiyoriy maydon tushib qoladi", () => {
    const base: Values = {
      price_cny: "10", qty: "5", china_cny_total: null, weight_kg: null, length_cm: "10", width_cm: null, height_cm: "10",
      cargo_usd_per_kg: null, cargo_usd_per_m3: null, extra_uzs: null, packaging_uzs: null, price: "90000", commission_pct: "15",
      tax_pct: null, ads_pct: null, target_margin_pct: null, cny_rate: null, usd_rate: null,
    };
    expect(toInput({ ...base, price: null })).toBeNull();
    expect(toInput({ ...base, qty: "0" })).toBeNull();
    expect(toInput(base)).toEqual({ price_cny: "10", qty: "5", price: "90000", commission_pct: "15" }); // o'lcham to'liq emas
    expect(toInput({ ...base, width_cm: "10" })).toMatchObject({ length_cm: "10", width_cm: "10", height_cm: "10" });
  });
});
