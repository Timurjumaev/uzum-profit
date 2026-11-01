// Bosh sahifa (M4, B4.1): hisob varag'i, davr chizig'i, grafik, "Diqqat talab qiladi", SKU, ko'rsatkichlar, drill-down.
// Butun ilova (marshrutlovchi + so'rovlar) soxta API ustida — `test/api.ts`.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import {
  dashboardData,
  DASHBOARD_ROUTE,
  EXPENSES_ROUTE,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  SALES_ROUTE,
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

const ledger = () => screen.getByRole("table", { name: "Hisob varagʻi: tushumdan sof foydagacha" });
const row = (name: string) => within(ledger()).getByRole("row", { name: new RegExp(`^${name}`) });
const requestUrls = (api: ReturnType<typeof mockApi>, path: string) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === path);

describe("hisob varag'i", () => {
  it("sof foyda (hero) va qatorlar tartibi: tushumdan sof foydagacha", async () => {
    await renderHome();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`Sof foyda, ${f.period("2026-10-01", "2026-10-26")}`);
    expect(norm(screen.getByTestId("net-profit").textContent!)).toBe(m("48393000.00"));
    const names = within(ledger())
      .getAllByRole("row")
      .map((r) => within(r).getByRole("rowheader").textContent);
    expect(names).toEqual(["Tushum", "Uzum komissiyasi", "Logistika", "Uzum toʻlovi", "Tannarx", "Reklama", "Saqlash", "Oʻz xarajatlarim", "Soliq", "Sof foyda"]);
    // oraliq summa va yakun — buxgalteriya chiziqlari (sinf), summalar valyutasiz va API'dan.
    expect(row("Uzum toʻlovi").className).toContain("is-subtotal");
    expect(row("Sof foyda").className).toContain("is-total");
    expect(within(row("Uzum komissiyasi")).getByText(n("-37284000.00"))).toBeTruthy();
    expect(within(row("Oʻz xarajatlarim")).getAllByText("0").length).toBeGreaterThan(0);
  });

  it("oldingi davrga nisbatan o'zgarish: ishora + nom bilan davr; rang = yo'nalish × yaxshimi", async () => {
    await renderHome();
    const hero = screen.getByText(/oldingi davrga nisbatan/);
    expect(norm(hero.textContent ?? "")).toContain(norm(f.period("2026-09-05", "2026-09-30")));
    expect(norm(hero.parentElement?.textContent ?? "")).toContain(ch("0.124274"));
    // Tushum o'sdi — yaxshi; komissiya (xarajat) o'sdi — yomon, ▲ kattalik bo'yicha; logistika kamaydi — yaxshi.
    expect(within(row("Tushum")).getByText(ch("0.129818")).className).toContain("ui-text--positive");
    const commission = within(row("Uzum komissiyasi")).getByText(ch("0.129818"));
    expect(commission.className).toContain("ui-text--negative");
    expect(within(row("Logistika")).getByText(ch("-0.067781")).className).toContain("ui-text--positive");
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

  it("mobilda yig'ilgan ko'rinish: 'Barcha qatorlar' tugmasi", async () => {
    await renderHome();
    const toggle = screen.getByRole("button", { name: "Barcha qatorlar" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(ledger().getAttribute("data-compact")).toBe("true");
    expect(within(ledger()).getAllByRole("row").filter((r) => r.className.includes("is-compact-hidden"))).toHaveLength(7);
    fireEvent.click(toggle);
    expect(ledger().getAttribute("data-compact")).toBeNull();
    expect(screen.getByRole("button", { name: "Qatorlarni yigʻish" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("har qatorda formula: F-raqam va manba", async () => {
    await renderHome();
    fireEvent.click(within(row("Soliq")).getByRole("button", { name: /Qanday hisoblanadi/ }));
    expect(screen.getByText("Soliq · F11")).toBeTruthy();
    expect(screen.getByText("Soliq profili boʻyicha")).toBeTruthy();
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
    // ADR-036: Jarayondagi sotuvlar hisobga kirgan — qaysi qismi yakuniy emasligi yoziladi; yo'q bo'lsa izoh yo'q.
    expect(norm(tile("Bugun").getByText(/shundan jarayonda/).textContent!)).toBe(`shundan jarayonda: 38 dona, ${m("5200000.00")}`);
    expect(tile("Oʻtgan oy").queryByText(/shundan jarayonda/)).toBeNull();
    expect(tile("Oy prognozi").queryByText(/shundan jarayonda/)).toBeNull();
    const hero = norm(screen.getByText(/^Shundan jarayonda:/).textContent!);
    expect(hero).toContain(`410 dona, ${m("61000000.00")} tushum — hali yakuniy emas.`);
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

  it("kunlik grafik: tushum (ustun) va sof foyda (chiziq), jadval ko'rinishi", async () => {
    await renderHome();
    const chart = await screen.findByRole("img", { name: /Kunlik tushum va sof foyda/ });
    expect(chart.getAttribute("aria-label")).toContain("Tushum");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    const table = await screen.findByRole("table", { name: /Kunlik tushum va sof foyda/ });
    expect(within(table).getAllByRole("row")).toHaveLength(4); // sarlavha + 3 kun
    // ADR-036: tushum ikki qatlam — yakunlangan va jarayonda (qismlar API'dan).
    expect(chart.getAttribute("aria-label")).toContain("Tushum: jarayonda");
    expect(within(table).getAllByText(/6\s800\s000/).length).toBeGreaterThan(0);
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

  it("ko'rsatkichlar: marja, ROI, bekor %, qaytish %, DRR, muzlagan pul, yo'ldagi tovar, kutilayotgan foyda", async () => {
    await renderHome();
    const kpis = within(screen.getByRole("region", { name: "Qoʻshimcha koʻrsatkichlar" }));
    const value = (label: string) => norm(kpis.getByText(label).closest(".ui-kpi")!.querySelector(".kpi")!.textContent ?? "");
    expect(value("Marja")).toBe(norm(f.percent("0.259400")));
    expect(value("ROI")).toBe(norm(f.percent("0.619000")));
    expect(value("Bekor boʻlish")).toBe(norm(f.percent("0.040000")));
    expect(value("Qaytarilish")).toBe(norm(f.percent("0.021000")));
    expect(value("Reklama ulushi (DRR)")).toBe(norm(f.percent("0.032200")));
    expect(value("Muzlagan pul")).toBe(m("92000000.00"));
    expect(value("Yoʻldagi tovar qiymati")).toBe(m("31000000.00"));
    expect(value("Jarayondagi sotuvlar")).toBe(m("61000000.00"));
    expect(norm(kpis.getByText(/oxirgi 90 kunda bunday sotuvlarning/).textContent!)).toBe(norm(`410 dona; oxirgi 90 kunda bunday sotuvlarning ${f.percent("0.870000")} yakunlangan`));
    expect(kpis.getByText("oʻrtacha sotilish: 42 kun")).toBeTruthy();
  });

  it("tannarxsiz qism marja yonida; ma'lumot yo'q — '—' va sababi (taxmin yashirilmaydi)", async () => {
    const base = dashboardData();
    const data = dashboardData({
      kpis: {
        ...base.kpis,
        margin: "0.300000",
        uncovered_share: "0.250000",
        roi: null,
        drr: null,
        pending: { units: 4, revenue: "500000.00", profit: "120000.00", uncovered_lines: 0, rate: null },
      },
    });
    await renderHome("/", { [DASHBOARD_ROUTE]: () => json(200, data) });
    const kpis = within(screen.getByRole("region", { name: "Qoʻshimcha koʻrsatkichlar" }));
    expect(kpis.getByText("Tannarxsiz qism: 25%")).toBeTruthy();
    expect(kpis.getByText("ROI").closest(".ui-kpi")!.querySelector(".kpi")!.textContent).toBe("—");
    // ADR-036: Jarayondagi sotuvlar — tushum (foydaga kirgan), R yo'q bo'lsa faqat dona.
    expect(norm(kpis.getByText("Jarayondagi sotuvlar").closest(".ui-kpi")!.querySelector(".kpi")!.textContent!)).toBe(m("500000.00"));
    expect(kpis.getByText("4 dona — foydaga kirgan, hali yakuniy emas")).toBeTruthy();
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

  it("ruscha: sarlavha va qatorlar", async () => {
    await renderHome("/", {}, "ru");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/^Чистая прибыль, /);
    expect(screen.getByRole("table", { name: /Расчётный лист/ })).toBeTruthy();
    expect(screen.getByText("Требует внимания")).toBeTruthy();
  });
});

describe("drill-down", () => {
  const sale = (id: string, over: Record<string, unknown> = {}) => ({
    id,
    shop_id: SHOP_A,
    sku_id: "d1",
    sku_title: "Sumka qora M",
    order_id: 1,
    external_id: 1,
    ordered_at: "2026-10-12T10:00:00Z",
    day: "2026-10-12",
    status: "TO_WITHDRAW",
    group: "completed",
    amount: 2,
    amount_returns: 0,
    return_cause: null,
    sell_price: "100000.00",
    revenue: "200000.00",
    commission: "40000.00",
    logistics: "10000.00",
    payout: "150000.00",
    cogs: "80000.00",
    gross_profit: "70000.00",
    cost_flags: [],
    recalculated_at: null,
    previous_cogs: null,
    ...over,
  });
  const page = (items: unknown[], next: string | null) => ({
    meta: dashboardData().meta,
    items,
    next_cursor: next,
    summary: { units: 2, canceled: 0, returns: 0, cancel_share: null, return_share: null },
  });
  const drawer = () => screen.getByRole("dialog");

  it("Tushum: yakunlangan va jarayondagi sotuv qatorlari, jami API qatoridan, kursor bilan 'Yana yuklash'", async () => {
    const { api } = await renderHome("/?from=2026-10-01&to=2026-10-20", {
      [SALES_ROUTE]: [
        () => json(200, page([sale("s1", { status: "PROCESSING", group: "processing" }), sale("s2", { sku_id: null, sku_title: null, day: "2026-10-11" })], "c2")),
        () => json(200, page([sale("s3", { day: "2026-10-10" })], null)),
      ],
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Tushum" }));
    const dlg = await screen.findByRole("dialog", { name: "Tushum" });
    expect(within(dlg).getByText(m("186420000.00"), { selector: ".kpi" })).toBeTruthy(); // jami — hisob varag'idagi qator, qayta hisoblanmagan
    expect(await within(dlg).findByText("Sumka qora M")).toBeTruthy();
    expect(within(dlg).getByText("SKU bogʻlanmagan")).toBeTruthy();
    expect(within(dlg).getAllByText("Jarayonda")).toHaveLength(1); // Jarayondagi qator belgilanadi (ADR-036)
    expect(within(dlg).getAllByText(n("200000.00"), { selector: "td" })).toHaveLength(2);
    const [first] = requestUrls(api, SALES_ROUTE.split(" ")[1]!);
    expect(first!.searchParams.get("counted")).toBe("true"); // Yakunlangan + Jarayonda (ADR-036)
    expect(first!.searchParams.get("group")).toBeNull();
    expect(first!.searchParams.get("start")).toBe("2026-10-01");
    expect(first!.searchParams.get("end")).toBe("2026-10-20");
    fireEvent.click(within(dlg).getByRole("button", { name: "Yana yuklash" }));
    await waitFor(() => expect(within(dlg).getAllByRole("row")).toHaveLength(4)); // sarlavha + 3
    expect(requestUrls(api, SALES_ROUTE.split(" ")[1]!)[1]!.searchParams.get("cursor")).toBe("c2");
    expect(within(dlg).queryByRole("button", { name: "Yana yuklash" })).toBeNull();
  });

  it("Tannarx: taxminiy belgi (F22) va qiymat ustuni tannarx", async () => {
    await renderHome("/", {
      [SALES_ROUTE]: () => json(200, page([sale("s1", { cost_flags: ["estimated"] }), sale("s2", { cogs: null })], null)),
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Tannarx" }));
    const dlg = await screen.findByRole("dialog", { name: "Tannarx" });
    await within(dlg).findByText("Sumka qora M", { exact: true, selector: "td" }).catch(() => undefined);
    expect(await within(dlg).findByText("Taxminiy", { selector: ".ui-badge" })).toBeTruthy();
    expect(within(dlg).getByRole("columnheader", { name: "Tannarx" })).toBeTruthy();
    expect(within(dlg).getByText(n("80000.00"))).toBeTruthy();
  });

  it("Uzum toifasi: shu toifa xarajatlari (chiqim — minus), toifa so'rovda", async () => {
    const expense = (id: string, type: string, amount: string) => ({
      id, shop_id: SHOP_A, external_id: 1, created_on: "2026-10-05T10:00:00Z", day: "2026-10-05", code: "Y1", raw_code: "Y1",
      category: "advertising", type, amount, name: "Reklama kampaniyasi", status: null, excluded: null, in_pnl: true, order_id: null, sale_item_id: null,
    });
    const { api } = await renderHome("/", {
      [EXPENSES_ROUTE]: () =>
        json(200, {
          meta: dashboardData().meta, uzum: [], uzum_total: "0.00", by_month: [], fines: [], own: [], own_total: "0.00", own_items: [],
          items: [expense("e1", "OUTCOME", "300000.00"), expense("e2", "INCOME", "50000.00")], next_cursor: null,
        }),
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Reklama" }));
    const dlg = await screen.findByRole("dialog", { name: "Reklama" });
    expect(await within(dlg).findAllByText("Reklama kampaniyasi")).toHaveLength(2);
    expect(within(dlg).getByText(n("-300000.00"))).toBeTruthy();
    expect(within(dlg).getByText(n("50000.00"))).toBeTruthy();
    expect(requestUrls(api, EXPENSES_ROUTE.split(" ")[1]!)[0]!.searchParams.get("category")).toBe("advertising");
  });

  it("hisoblanadigan qator (Soliq): yozuv yo'q, faqat formula; sotuv so'ralmaydi", async () => {
    const { api } = await renderHome();
    fireEvent.click(within(ledger()).getByRole("button", { name: "Soliq" }));
    const dlg = await screen.findByRole("dialog", { name: "Soliq" });
    expect(within(dlg).getByText(/Bu qator boshqa qatorlardan hisoblanadi/)).toBeTruthy();
    expect(within(dlg).getByText(/F11: Soliq profili boʻyicha/)).toBeTruthy();
    expect(api.count(SALES_ROUTE)).toBe(0);
  });

  it("ruxsat yo'q (xarajatlar sozlama ruxsati) — drawer ichida xato matni; Esc yopadi", async () => {
    await renderHome("/", { [EXPENSES_ROUTE]: () => problem(403, "forbidden") });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Saqlash" }));
    const dlg = await screen.findByRole("dialog", { name: "Saqlash" });
    expect((await within(dlg).findByRole("alert")).textContent).toContain("Bu sahifaga ruxsatingiz yoʻq.");
    fireEvent.keyDown(drawer(), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("kirish imkoniyati", () => {
  it("axe-core: jiddiy xato 0 (drawer ochiq ham)", async () => {
    await renderHome();
    const run = async () => {
      const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
      return result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
    };
    expect(await run()).toEqual([]);
    fireEvent.click(within(ledger()).getByRole("button", { name: "Soliq" }));
    await screen.findByRole("dialog", { name: "Soliq" });
    expect(await run()).toEqual([]);
  }, 30_000);
});
