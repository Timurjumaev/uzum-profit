// Bosh sahifa (M4, ADR-037): uch raqam (yakunlangan + kutilayotgan = jami sof foyda), davr chizig'i, grafik, "Diqqat talab
// qiladi", SKU, ko'rsatkichlar. Hisob varag'i va drill-down — Foyda sahifasida (`pnl.test.tsx`). Butun ilova
// (marshrutlovchi + so'rovlar) soxta API ustida — `test/api.ts`.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import {
  dashboardData,
  DASHBOARD_ROUTE,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  SHOP_A,
  SYNC_ROUTE,
  syncStatus,
  type Routes,
} from "../../test/api";

const f = formatterFor("uz-Latn");
// Testing Library tugun matnidagi bo'shliqlarni (NBSP, U+202F) oddiy bo'shliqqa keltiradi — kutilgan matn ham.
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const m = (value: string) => norm(f.money(value));
const n = (value: string) => norm(f.money(value, { unit: false }));
const ch = (value: string) => norm(f.change(value));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function renderHome(path = "/", routes: Routes = {}, lang: "uz-Latn" | "ru" = "uz-Latn") {
  // Profil tili tanlanmagan til o'rniga qo'llanadi — shuning uchun profilni ham tilga moslaymiz.
  const api = mockApi({ [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: lang } }), ...routes });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, lang)} />);
  await screen.findByTestId("net-profit");
  return { api, history };
}

const card = (testId: string) => within(screen.getByTestId(testId).closest("li")!);
const requestUrls = (api: ReturnType<typeof mockApi>, path: string) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === path);

describe("uch raqam (ADR-037)", () => {
  it("sarlavha va tenglama: yakunlangan + kutilayotgan = jami sof foyda (summalar API'dan)", async () => {
    await renderHome();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`Sof foyda, ${f.period("2026-10-01", "2026-10-26")}`);
    expect(norm(screen.getByTestId("net-done").textContent!)).toBe(m("31508700.00"));
    expect(norm(screen.getByTestId("net-expected").textContent!)).toBe(m("16884300.00"));
    expect(norm(screen.getByTestId("net-profit").textContent!)).toBe(m("48393000.00"));
    const labels = screen.getAllByRole("heading", { level: 2 }).slice(0, 3).map((h) => h.firstChild?.textContent);
    expect(labels).toEqual(["Yakunlangan sof foyda", "Kutilayotgan sof foyda", "Jami sof foyda"]);
    // Amal belgilari — bezak (ekran o'quvchi ro'yxatni 3 ta element sifatida o'qiydi).
    expect([...document.querySelectorAll(".home-sum__op")].map((x) => x.textContent)).toEqual(["+", "="]);
    expect(screen.getByTestId("net-done").className).toContain("ui-text--positive");
  });

  it("izohlar: yakunlangan va jarayondagi dona, tushum, yakunlanish ulushi (fakt), taxminiy logistika", async () => {
    await renderHome();
    expect(norm(card("net-done").getByText(/^Yakunlangan sotuvlar:/).textContent!)).toBe(`Yakunlangan sotuvlar: 830 dona, tushum ${m("125420000.00")}`);
    expect(norm(card("net-expected").getByText(/^Jarayonda:/).textContent!)).toBe(`Jarayonda: 410 dona, tushum ${m("61000000.00")}`);
    expect(norm(card("net-expected").getByText(/bunday sotuvlarning/).textContent!)).toBe(norm(`Oxirgi 90 kunda bunday sotuvlarning ${f.percent("0.870000")} yakunlangan`));
    expect(card("net-expected").getByText("Logistika 380 dona uchun taxminiy — Uzum hali yozmagan")).toBeTruthy();
    expect(norm(card("net-profit").getByText(/oldingi davrga nisbatan/).textContent!)).toContain(norm(f.period("2026-09-05", "2026-09-30")));
    expect(norm(card("net-profit").getByText(ch("0.124274")).textContent!)).toBe(ch("0.124274"));
    expect(card("net-profit").getByText(norm(`Marja ${f.percent("0.259400")}`))).toBeTruthy();
  });

  it("formula: yakunlangan (F12), kutilayotgan (F16, taxminiy sababi bilan), jami", async () => {
    await renderHome();
    fireEvent.click(card("net-expected").getByRole("button", { name: /Qanday hisoblanadi/ }));
    expect(screen.getByText("Kutilayotgan sof foyda · F16")).toBeTruthy();
    expect(screen.getByText(/xuddi yakunlanganlar kabi: tushum − komissiya − logistika − tannarx/)).toBeTruthy();
    expect(screen.getByText(/10 kun ichida qaytarsa kamayadi/)).toBeTruthy();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    fireEvent.click(card("net-profit").getByRole("button", { name: /Qanday hisoblanadi/ }));
    expect(screen.getByText("Yakunlangan sof foyda + kutilayotgan sof foyda")).toBeTruthy();
  });

  it("jarayondagi sotuv yo'q va yakunlangan yo'q — bo'sh matnlar; zarar — qizil", async () => {
    const base = dashboardData();
    const data = dashboardData({
      statement: { ...base.statement, units_done: 0, net_profit_done: "-650000.00" },
      expected: { ...base.expected, units: 0, net_profit: "0.00", logistics_estimated_units: 0 },
    });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, data) });
    expect(card("net-done").getByText("Bu davrda yakunlangan sotuv hali yoʻq")).toBeTruthy();
    expect(screen.getByTestId("net-done").className).toContain("ui-text--negative");
    expect(card("net-expected").getByText("Jarayondagi sotuv yoʻq")).toBeTruthy();
    expect(card("net-expected").queryByText(/taxminiy/)).toBeNull();
  });

  it("yakunlanish ulushi uchun ma'lumot kam — shunday deyiladi (R o'ylab topilmaydi)", async () => {
    const base = dashboardData();
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, dashboardData({ expected: { ...base.expected, rate: null } })) });
    expect(card("net-expected").getByText("Yakunlanish ulushi uchun maʼlumot hali kam")).toBeTruthy();
  });

  it("kutilayotgan reklama taxmini (F42) kartochkada aytiladi", async () => {
    const base = dashboardData();
    const expected = { ...base.expected, uzum_estimated: { advertising: "6000.00" } };
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, dashboardData({ expected })) });
    expect(norm(card("net-expected").getByText(/^Reklama .* taxminiy/).textContent!)).toContain(m("6000.00"));
  });

  it("'Qanday hisoblandi' — Foyda sahifasiga (filtrlar saqlanadi); bosh sahifada hisob varag'i yo'q", async () => {
    await renderHome("/?from=2026-10-01&to=2026-10-20");
    const how = screen.getByRole("link", { name: "Qanday hisoblandi — «Foyda» sahifasida" });
    expect(how.getAttribute("href")).toBe("/pnl?from=2026-10-01&to=2026-10-20");
    expect(screen.queryByRole("table", { name: /Hisob varagʻi/ })).toBeNull();
  });

  it("filtrlar URL'dan API'ga: davr va do'kon", async () => {
    const { api } = await renderHome(`/?from=2026-10-01&to=2026-10-20&shop=${SHOP_A}`);
    const [call] = requestUrls(api, DASHBOARD_ROUTE.split(" ")[1]!);
    expect(call!.searchParams.get("start")).toBe("2026-10-01");
    expect(call!.searchParams.get("end")).toBe("2026-10-20");
    expect(call!.searchParams.getAll("shop")).toEqual([SHOP_A]);
  });

  it("tannarxsiz sotuvlar bo'lsa sariq banner va 'Tannarx kiritish'; yo'q bo'lsa banner yo'q", async () => {
    await renderHome();
    expect(screen.queryByText("Tannarxsiz sotuvlar hisobga kirmadi")).toBeNull();
    cleanup();
    const data = dashboardData({ attention: { ...dashboardData().attention, uncosted_lines: 12, uncosted_revenue: "1240000.00" } });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, data) });
    const banner = screen.getByText("Tannarxsiz sotuvlar hisobga kirmadi").closest(".ui-banner")!;
    expect(banner.className).toContain("ui-tone--warning");
    expect(norm(banner.textContent!)).toContain(`12 ta sotuv (${m("1240000.00")})`);
    expect(within(banner as HTMLElement).getByRole("link", { name: "Tannarx kiritish" }).getAttribute("href")).toBe("/products");
  });
});

describe("davr chizig'i va grafik", () => {
  const tile = (name: string) => {
    const strip = screen.getByRole("region", { name: "Davrlar" });
    return within(within(strip).getByRole("heading", { level: 3, name: new RegExp(`^${name}`) }).closest("li")!);
  };

  it("Bugun, Kecha, Shu oy, Oy prognozi, O'tgan oy — tushum, sof foyda, dona", async () => {
    await renderHome();
    const strip = screen.getByRole("region", { name: "Davrlar" });
    expect(within(strip).getAllByRole("heading", { level: 3 }).map((h) => h.firstChild?.textContent?.trim())).toEqual([
      "Bugun",
      "Kecha",
      "Shu oy",
      "Oy prognozi",
      "Oʻtgan oy",
    ]);
    expect(tile("Bugun").getByText(m("5200000.00"))).toBeTruthy();
    expect(tile("Bugun").getByText("38 dona")).toBeTruthy();
    expect(tile("Kecha").getByText(m("1810000.00"))).toBeTruthy();
    expect(tile("Oʻtgan oy").getByText(m("47000000.00"))).toBeTruthy();
    // ADR-037: sof foyda ostida yakunlangan va kutilayotgan qismlari (API'dan); kutilayotgan yo'q — izoh yo'q.
    expect(norm(tile("Kecha").getByText(/^yakunlangan /).textContent!)).toBe(`yakunlangan ${m("60000.00")} · kutilayotgan ${m("1750000.00")}`);
    expect(tile("Oʻtgan oy").queryByText(/kutilayotgan/)).toBeNull();
    expect(tile("Oy prognozi").queryByText(/kutilayotgan/)).toBeNull();
    // Prognoz (run-rate) API'dan; dona butun songa yaxlitlanadi.
    expect(tile("Oy prognozi").getByText(m("216000000.00"))).toBeTruthy();
    expect(tile("Oy prognozi").getByText("1 437 dona")).toBeTruthy();
  });

  it("zarar — qizil matn; prognoz yo'q (oyning 1-kuni) — 'Maʼlumot yetarli emas'", async () => {
    const data = dashboardData({
      forecast: { revenue: null, net_profit: null, units: null },
      periods: dashboardData().periods.map((p) => (p.key === "today" ? { ...p, net_profit: "-120000.00" } : p)),
    });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, data) });
    expect(tile("Bugun").getByText(m("-120000.00")).className).toContain("ui-text--negative");
    expect(tile("Oy prognozi").getByText("Maʼlumot yetarli emas")).toBeTruthy();
  });

  it("kunlik grafik: sof foyda yakunlangan va kutilayotgan qatlamlarda; 'Tushum' — yakunlangan va jarayonda; jadval", async () => {
    await renderHome();
    const chart = await screen.findByRole("img", { name: /Kunlik sof foyda: yakunlangan va kutilayotgan/ });
    expect(chart.getAttribute("aria-label")).toContain("Kutilayotgan");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    const table = await screen.findByRole("table", { name: /Kunlik sof foyda/ });
    expect(within(table).getAllByRole("row")).toHaveLength(4); // sarlavha + 3 kun
    expect(within(table).getAllByText(/1\s750\s000/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("radio", { name: "Tushum" }));
    const revenue = await screen.findByRole("table", { name: /Kunlik tushum: yakunlangan va jarayonda/ });
    expect(within(revenue).getAllByText(/6\s800\s000/).length).toBeGreaterThan(0);
  });
});

describe("diqqat talab qiladi", () => {
  it("ustuvorlik tartibida, har biri tegishli sahifaga (filtrlar saqlanadi)", async () => {
    const data = dashboardData({ attention: { uncosted_lines: 12, uncosted_revenue: "1240000.00", loss_skus: 1, stock_critical: 2, stock_high: 3, recalculated: 4 } });
    await renderHome(`/?from=2026-10-01&to=2026-10-20`, { [DASHBOARD_ROUTE]: () => json(200, data) });
    const section = screen.getByRole("region", { name: "Diqqat talab qiladi" });
    const items = within(section).getAllByRole("listitem");
    expect(items.map((li) => norm(li.textContent ?? "").replace(/Koʻrish$/, ""))).toEqual([
      `Tannarxsiz sotuvlar: 12 ta (${m("1240000.00")})`,
      "Kritik zaxira (tez tugaydi): 2 ta SKU",
      "Zaxira tugashga yaqin: 3 ta SKU",
      "Zarar bilan sotilayotgan SKU: 1 ta",
      "Tannarxi qayta hisoblangan sotuvlar: 4 ta",
    ]);
    const href = within(items[1]!).getByRole("link", { name: "Koʻrish" }).getAttribute("href")!;
    expect(href.startsWith("/inventory")).toBe(true);
    expect(href).toContain("from=2026-10-01");
  });

  it("sinxron xatosi (do'kon sog'lom emas) ro'yxatga chiqadi; hammasi joyida — bo'sh holat matni", async () => {
    const base = syncStatus();
    const sick = syncStatus({ healthy: false, shops: [{ ...base.shops[0]!, healthy: false, errors_24h: 3 }, base.shops[1]!] });
    await renderHome("/", {
      [DASHBOARD_ROUTE]: () => json(200, dashboardData({ attention: { uncosted_lines: 0, uncosted_revenue: "0.00", loss_skus: 0, stock_critical: 0, stock_high: 0, recalculated: 0 } })),
      [SYNC_ROUTE]: () => json(200, sick),
    });
    const section = screen.getByRole("region", { name: "Diqqat talab qiladi" });
    await waitFor(() => expect(within(section).getByText("Sinxronda muammo: 1 ta doʻkon")).toBeTruthy());
    expect(within(section).getByRole("link", { name: "Koʻrish" }).getAttribute("href")).toContain("/status");
    cleanup();
    await renderHome("/", {
      [DASHBOARD_ROUTE]: () => json(200, dashboardData({ attention: { uncosted_lines: 0, uncosted_revenue: "0.00", loss_skus: 0, stock_critical: 0, stock_high: 0, recalculated: 0 } })),
    });
    expect(screen.getByText("Hozir diqqat talab qiladigan narsa yoʻq.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Koʻrish" })).toBeNull();
  });
});

describe("eng foydali 5 / zarar 5 va ko'rsatkichlar", () => {
  it("SKU jadvallari: nom (SKU yoki tovar nomi), dona, sof foyda rangi; mobilda tab", async () => {
    await renderHome();
    const top = screen.getByRole("table", { name: "Eng foydali 5" });
    expect(within(top).getByText("Sumka qora M")).toBeTruthy();
    expect(within(top).getByText("Hamyon")).toBeTruthy(); // SKU nomi yo'q — tovar nomi
    expect(within(top).getByText(n("9000000.00")).className).toContain("ui-text--positive");
    const bottom = screen.getByRole("table", { name: "Zarar qilayotgan 5" });
    expect(within(bottom).getByText(n("-250000.00")).className).toContain("ui-text--negative");
    // Tablar (mobil): tanlangan panel `data-tab` bilan boshqariladi.
    const tabs = screen.getByRole("tablist");
    expect(within(tabs).getByRole("tab", { name: "Eng foydali 5" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(within(tabs).getByRole("tab", { name: "Zarar qilayotgan 5" }));
    expect(tabs.parentElement?.getAttribute("data-tab")).toBe("bottom");
    expect(within(tabs).getByRole("tab", { name: "Zarar qilayotgan 5" }).getAttribute("aria-selected")).toBe("true");
  });

  it("bo'sh ro'yxatlar", async () => {
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, dashboardData({ top: [], bottom: [] })) });
    expect(screen.getByText("Bu davrda foyda keltirgan SKU yoʻq.")).toBeTruthy();
    expect(screen.getByText("Zarar qilayotgan SKU yoʻq.")).toBeTruthy();
  });

  it("KPI sarhisob (ADR-043): 4 guruh, 24 kartochka — qiymat, oldingi davr, o'zgarish (ulushda punkt), rang", async () => {
    await renderHome();
    const region = within(screen.getByRole("region", { name: "Koʻrsatkichlar sarhisobi" }));
    for (const name of ["Buyurtmalar va tushum", "Uzum ushlab qolgani va foyda", "Qaytarilgan va bekor qilingan", "Oʻrtacha koʻrsatkichlar"]) {
      expect(region.getByRole("heading", { name })).toBeTruthy();
    }
    expect(region.getAllByRole("listitem").filter((li) => li.classList.contains("home-card"))).toHaveLength(24);
    const kpi = (key: string) => screen.getByTestId(`kpi-${key}`);
    const value = (key: string) => norm(kpi(key).querySelector(".home-card__value")!.textContent ?? "");
    expect(value("revenue")).toBe(m("186420000.00"));
    expect(value("gross_revenue")).toBe(m("215420000.00"));
    expect(value("orders")).toBe("1 610");
    expect(value("units_per_order")).toBe("1,13");
    expect(value("cancel_share")).toBe(norm(f.percent("0.181141")));
    expect(norm(kpi("revenue").textContent ?? "")).toContain(`oldingi: ${m("190000000.00")}`);
    // Tushum kamaydi — yomon (qizil); bekor ulushi o'sdi — punktda, yomon; xarajat ulushi o'sdi — yomon.
    const change = (key: string) => kpi(key).querySelector(".home-card__change")!;
    expect(norm(change("revenue").textContent ?? "")).toBe("▼ 1,9%");
    expect(change("revenue").className).toContain("ui-text--negative");
    expect(norm(change("cancel_share").textContent ?? "")).toBe("▲ 2,6 punkt");
    expect(change("cancel_share").className).toContain("ui-text--negative");
    expect(change("uzum_costs_share").className).toContain("ui-text--negative");
    expect(change("net_profit").className).toContain("ui-text--positive");
    expect(kpi("average_price").querySelector(".home-card__change")!.className).toContain("ui-text--neutral");
    // Asosiy kartochkalar ajratilgan; har kartochkada formula.
    expect(kpi("revenue").className).toContain("home-card--key");
    expect(kpi("net_profit").className).toContain("home-card--key");
    fireEvent.click(within(kpi("cancel_share")).getByRole("button", { name: /Bekor boʻlish ulushi \(soni\)/ }));
    expect(screen.getByText(/F17/)).toBeTruthy();
    // Davrlar: joriy va oldingi.
    expect(region.getByText(/Joriy davr/)).toBeTruthy();
    expect(region.getByText(/Oldingi davr/)).toBeTruthy();
  });

  it("buyurtmadan sof foydagacha (F49): bo'laklar o'ngdan chapga, summa / ulush; nol qator yashiriladi", async () => {
    await renderHome();
    const flow = screen.getByRole("figure", { name: "Buyurtmadan sof foydagacha" });
    const steps = [...flow.querySelectorAll(".home-flow__step")].map((li) => norm(li.querySelector(".home-flow__name")!.textContent ?? ""));
    expect(steps).toEqual(["Buyurtmalar summasi", "Bekor qilingan", "Qaytarilgan", "Uzum ushlab qolgan", "Tannarx", "Oʻz xarajatlar", "Soliq", "Sof foyda"]);
    const bar = (key: string) => flow.querySelector<HTMLElement>(`.home-flow__step--${key} .home-flow__bar > span`)!.style;
    expect([bar("gross_revenue").insetInlineStart, bar("gross_revenue").inlineSize]).toEqual(["0%", "100%"]);
    // Bekor — eng o'ngda (90,79–100%), sof foyda — chapda (0–22,46%).
    expect([bar("cancel_revenue").insetInlineStart, bar("cancel_revenue").inlineSize]).toEqual(["90.79%", "9.21%"]);
    expect([bar("net_profit").insetInlineStart, bar("net_profit").inlineSize]).toEqual(["0%", "22.46%"]);
    const row = (key: string) => flow.querySelector(`.home-flow__step--${key}`)!;
    expect(norm(row("gross_revenue").querySelector(".home-flow__share")!.textContent ?? "")).toBe("/ 100%");
    expect(norm(row("cogs").querySelector(".home-flow__value")!.textContent ?? "")).toBe(m("70000000.00"));
    expect(norm(row("cogs").querySelector(".home-flow__share")!.textContent ?? "")).toBe("/ 32,5%");
    expect(within(flow as HTMLElement).queryByText(/Tannarxi kiritilmagan/)).toBeNull();
  });

  it("buyurtmadan sof foydagacha: zarar chapdan qizil, tannarxsiz qism ko'rinadi", async () => {
    const base = dashboardData();
    const flow = base.summary.flow.map((x) =>
      x.key === "uncosted" ? { ...x, value: "10000000.00", share: "0.046421" } : x.key === "net_profit" ? { ...x, value: "-20000000.00", share: "-0.092842" } : x,
    );
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, dashboardData({ summary: { ...base.summary, flow } })) });
    const fig = screen.getByRole("figure", { name: "Buyurtmadan sof foydagacha" });
    const net = fig.querySelector<HTMLElement>(".home-flow__step--net_profit")!;
    expect(net.className).toContain("is-negative");
    const span = net.querySelector<HTMLElement>(".home-flow__bar > span")!.style;
    expect([span.insetInlineStart, span.inlineSize]).toEqual(["0%", "9.28%"]);
    expect(fig.querySelector(".home-flow__step--uncosted")).toBeTruthy();
    expect(within(fig as HTMLElement).getByText(/tannarxi yoʻq sotuvlardan qolgan pul/)).toBeTruthy();
  });

  it("tovardagi pul: muzlagan pul va yo'ldagi tovar (davrga bog'liq emas)", async () => {
    await renderHome();
    const kpis = within(screen.getByRole("region", { name: "Tovardagi pul" }));
    const value = (label: string) => norm(kpis.getByText(label).closest(".ui-kpi")!.querySelector(".kpi")!.textContent ?? "");
    expect(value("Muzlagan pul")).toBe(m("92000000.00"));
    expect(value("Yoʻldagi tovar qiymati")).toBe(m("31000000.00"));
    expect(kpis.getByText("oʻrtacha sotilish: 42 kun")).toBeTruthy();
    // Kutilayotgan sof foyda — yuqoridagi uch raqamda (ADR-037), bu yerda takrorlanmaydi.
    expect(kpis.queryByText("Jarayondagi sotuvlar")).toBeNull();
  });

  it("tannarxsiz qism marja kartochkasida; qiymat yo'q — '—'; chegaradan oshgan ulush ogohlantiriladi", async () => {
    const base = dashboardData();
    const groups = base.summary.groups.map((g) => ({
      ...g,
      cards: g.cards.map((c) =>
        c.key === "roi" ? { ...c, value: null, previous: null, change: null, series: [null, null, null] } : c.key === "cancel_share" ? { ...c, warn: true } : c,
      ),
    }));
    const data = dashboardData({ kpis: { ...base.kpis, uncovered_share: "0.250000" }, summary: { ...base.summary, groups } });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, data) });
    const kpi = (key: string) => screen.getByTestId(`kpi-${key}`);
    expect(within(kpi("margin")).getByText("Tannarxsiz qism: 25%")).toBeTruthy();
    expect(kpi("roi").querySelector(".home-card__value")!.textContent).toBe("—");
    expect(kpi("roi").querySelector(".home-card__change")).toBeNull();
    expect(kpi("cancel_share").className).toContain("home-card--warn");
    expect(within(kpi("cancel_share")).getByText(/Sozlangan chegaradan yuqori/)).toBeTruthy();
    expect(within(kpi("cancel_share")).getByRole("link", { name: "Chegarani oʻzgartirish" }).getAttribute("href")).toContain("/settings");
    expect(kpi("return_share").className).not.toContain("home-card--warn");
  });
});

describe("holatlar", () => {
  const noSales = () => {
    const base = dashboardData();
    return dashboardData({ statement: { ...base.statement, lines: 0 } });
  };

  it("sotuv yo'q + sinxron sog'lom — 'Bu davrda sotuv yo'q'", async () => {
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, noSales()) });
    expect(screen.getByRole("heading", { name: "Bu davrda sotuv yoʻq" })).toBeTruthy();
  });

  it("sotuv yo'q + sinxron muammoli — 'yo'q' deb aytilmaydi (tamoyil 8)", async () => {
    const base = syncStatus();
    const sick = syncStatus({ healthy: false, shops: [{ ...base.shops[0]!, healthy: false, errors_24h: 2 }, base.shops[1]!] });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, noSales()), [SYNC_ROUTE]: () => json(200, sick) });
    await screen.findByRole("heading", { name: "Maʼlumot toʻliq emas" });
    expect(screen.queryByRole("heading", { name: "Bu davrda sotuv yoʻq" })).toBeNull();
    const empty = screen.getByRole("heading", { name: "Maʼlumot toʻliq emas" }).closest("section")!;
    expect(within(empty).getByRole("link", { name: "Maʼlumotlar holati" }).getAttribute("href")).toContain("/status");
  });

  it("sotuv yo'q + hali sinxron bo'lmagan — 'Maʼlumot hali yuklanmagan'", async () => {
    const fresh = { orders: null, expenses: null, products: null, returns: null };
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, noSales()), [SYNC_ROUTE]: () => json(200, syncStatus({ freshness: fresh })) });
    await screen.findByRole("heading", { name: "Maʼlumot hali yuklanmagan" });
  });

  it("o'tgan yil bilan solishtirish — hozircha oldingi davr ekani aytiladi", async () => {
    await renderHome("/?cmp=lastYear");
    expect(screen.getByText(/Oʻtgan yil bilan solishtirish keyinroq qoʻshiladi/)).toBeTruthy();
  });

  it("server xatosi — xato bannerida sabab va 'Qayta urinish'", async () => {
    const api = mockApi({ [DASHBOARD_ROUTE]: [() => problem(403, "forbidden"), () => json(200, dashboardData())] });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/"] }), "uz-Latn")} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Bu sahifaga ruxsatingiz yoʻq.");
    fireEvent.click(within(alert).getByRole("button", { name: "Qayta urinish" }));
    await screen.findByTestId("net-profit");
    expect(api.count(DASHBOARD_ROUTE)).toBe(2);
  });

  it("ruscha: sarlavha va uch raqam", async () => {
    await renderHome("/", {}, "ru");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/^Чистая прибыль, /);
    expect(screen.getByText("Фактическая чистая прибыль")).toBeTruthy();
    expect(screen.getByText("Ожидаемая чистая прибыль")).toBeTruthy();
    expect(screen.getByText("Итого чистая прибыль")).toBeTruthy();
    expect(screen.getByText("Требует внимания")).toBeTruthy();
  });
});

describe("kirish imkoniyati", () => {
  it("axe-core: jiddiy xato 0 (formula ochiq ham)", async () => {
    await renderHome();
    const run = async () => {
      const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
      return result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
    };
    expect(await run()).toEqual([]);
    fireEvent.click(card("net-done").getByRole("button", { name: /Qanday hisoblanadi/ }));
    expect(await run()).toEqual([]);
  }, 30_000);
});
