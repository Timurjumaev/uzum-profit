// Mahsulotlar (M6, B4.3): jadval (ustunlar, qidiruv, filtrlar, saralash URL'da, ustun tanlash, ko'rinishlar),
// SKU sahifasi (KPI, tarix, lotlar, qaytishlar), unit kalkulyator va tovarga bog'lash. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { ITEMS_ROUTE, json, linkRoute, ME, ME_ROUTE, mockApi, ORG_ID, problem, skuRoute, SKUS_ROUTE, UNIT_CALC_ROUTE, type Routes } from "../../test/api";
import { ITEM_1, SECOND, SKU_1, SKU_2, skuDetail, skuRow, skusData, unitCalc } from "../../test/products";
import { DEFAULT_COLUMNS, fillDays } from "./model";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const n = (value: string) => norm(f.money(value, { unit: false }));
const PATH = "/products?from=2026-09-01&to=2026-10-31";
const CAPTION = "Mahsulotlar: SKU boʻyicha sotuv va foyda";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [SKUS_ROUTE]: () => json(200, skusData()),
    [skuRoute(SKU_1)]: () => json(200, skuDetail()),
    [UNIT_CALC_ROUTE]: () => json(200, unitCalc()),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

async function renderTable(routes: Routes = {}) {
  const out = await renderAt(PATH, routes);
  await screen.findByRole("table", { name: CAPTION });
  return out;
}

const table = () => screen.getByRole("table", { name: CAPTION });
const headers = () => within(table()).getAllByRole("columnheader").map((h) => h.textContent);
const skusUrls = (api: ReturnType<typeof mockApi>) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === `/api/v1/orgs/${ORG_ID}/skus`);

describe("jadval", () => {
  it("standart ustunlar, qatorlar, nom — SKU sahifasiga havola, qiymatsiz katak — tire", async () => {
    await renderTable();
    expect(headers().map((h) => h!.replace(/Qanday hisoblanadi.*$/, "").trim())).toEqual(
      expect.arrayContaining(["Mahsulot", "Doʻkon", "Dona", "Tushum", "Foyda/dona", "Marja", "ROI", "Qoldiq", "Holat"]),
    );
    expect(headers().join(" ")).not.toContain("Komissiya"); // ixtiyoriy ustun
    const rows = within(table()).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    const first = rows[0]!;
    expect(within(first).getByRole("link", { name: "Oʻyinchoq mashina qizil" }).getAttribute("href")).toBe(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`);
    expect(within(first).getByText(n("1200000.00"))).toBeTruthy();
    expect(within(first).getByText("Foydali")).toBeTruthy();
    const second = rows[1]!;
    expect(within(second).getByText("Maʼlumot yoʻq")).toBeTruthy();
    expect(within(second).getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Mahsulotlar");
    expect(screen.getByText("Jami 2 ta SKU")).toBeTruthy();
  });

  it("B4.42: bitta 'Tannarx/dona' ustuni — sotuv bo'lsa davr o'rtachasi, bo'lmasa oxirgi partiya izoh bilan; 'Oxirgi partiya' ustuni yo'q", async () => {
    const rows = skusData().items.map((r, i) => (i === 0 ? { ...r, cogs_per_unit: null, units: 0, unit_cost: "120000.00", unit_cost_source: "transit" as const } : r));
    await renderTable({ [SKUS_ROUTE]: () => json(200, skusData({ items: rows })) });
    const names = headers().map((h) => h!.replace(/Qanday hisoblanadi.*$/, "").trim());
    expect(names).toContain("Tannarx/dona");
    expect(names).not.toContain("Oxirgi partiya");
    const [first, second] = within(table()).getAllByRole("row").slice(1);
    expect(norm(first!.textContent!)).toContain(`${n("120000.00")} (yoʻldagi partiya)`); // davrda sotuv yo'q — partiya tannarxi
    expect(within(second!).getAllByText("—").length).toBeGreaterThan(0); // tovarga bog'lanmagan SKU
    cleanup();
    // Partiya yo'q, boshlang'ich narx: "(boshlang'ich)"; oxirgi partiya: "(oxirgi partiya)"; sotuvdan — izohsiz.
    const opened = skusData().items.map((r, i) => (i === 0 ? { ...r, unit_cost: "10000.00", unit_cost_source: "opening" as const } : r));
    await renderTable({ [SKUS_ROUTE]: () => json(200, skusData({ items: opened })) });
    expect(norm(within(table()).getAllByRole("row")[1]!.textContent!)).toContain(`${n("10000.00")} (boshlangʻich)`);
    cleanup();
    const last = skusData().items.map((r, i) => (i === 0 ? { ...r, unit_cost: "90000.00", unit_cost_source: "lot" as const } : r));
    await renderTable({ [SKUS_ROUTE]: () => json(200, skusData({ items: last })) });
    expect(norm(within(table()).getAllByRole("row")[1]!.textContent!)).toContain(`${n("90000.00")} (oxirgi partiya)`);
    cleanup();
    await renderTable();
    expect(norm(within(table()).getAllByRole("row")[1]!.textContent!)).not.toContain("partiya)");
  });

  it("B4.47: qisman tannarxsiz SKU — marja va holat yonida 'tannarxsiz N%' (izoh bilan); to'liq tannarxli SKU'da yo'q", async () => {
    const items = [skuRow({ uncovered_share: "0.250000", uncovered_lines: 2 }), skuRow({ sku_id: SKU_2, title: "Kruzhka", item_id: null })];
    await renderTable({ [SKUS_ROUTE]: () => json(200, skusData({ items })) });
    const [first, second] = within(table()).getAllByRole("row").slice(1);
    const marks = within(first!).getAllByText(/tannarxsiz 25%/);
    expect(marks).toHaveLength(2); // marja va holat
    expect(marks[0]!.getAttribute("title")).toContain("2 ta sotuv");
    expect(within(second!).queryByText(/tannarxsiz/)).toBeNull();
    cleanup();
    // Hammasi tannarxsiz ("Ma'lumot yo'q"): marja "—" yonida ulush, holatda takrorlanmaydi.
    await renderTable();
    const blind = within(table()).getAllByRole("row")[2]!;
    expect(within(blind).getAllByText(/tannarxsiz 100%/)).toHaveLength(1);
  });

  it("so'rov: davr, saralash (standart -revenue), limit; ustun sarlavhasi bosilsa URL va so'rov o'zgaradi", async () => {
    const { api, history } = await renderTable();
    const [first] = skusUrls(api);
    expect(first!.searchParams.get("sort")).toBeNull(); // standart — URL va so'rovda yo'q
    expect(first!.searchParams.get("start")).toBe("2026-09-01");
    const revenue = within(table()).getByRole("columnheader", { name: /^Tushum/ });
    expect(revenue.getAttribute("aria-sort")).toBe("descending");
    fireEvent.click(within(revenue).getByRole("button", { name: /^Tushum/ }));
    await waitFor(() => expect(history.location.search).toContain("sort=revenue"));
    await waitFor(() => expect(skusUrls(api).some((u) => u.searchParams.get("sort") === "revenue")).toBe(true));
    fireEvent.click(within(table()).getByRole("button", { name: /^Foyda\/dona/ }));
    await waitFor(() => expect(history.location.search).toContain("sort=-profit_per_unit"));
    fireEvent.click(within(table()).getByRole("button", { name: /^Mahsulot/ }));
    await waitFor(() => expect(history.location.search).toContain("sort=title")); // nom — o'sish tartibida
  });

  it("qidiruv kechikish bilan URL va API'ga; filtr tanlovi; hech narsa topilmasa — tozalash", async () => {
    const { api, history } = await renderTable();
    fireEvent.change(screen.getByRole("searchbox", { name: "Mahsulot qidirish" }), { target: { value: "mashina" } });
    await waitFor(() => expect(history.location.search).toContain("q=mashina"));
    await waitFor(() => expect(skusUrls(api).some((u) => u.searchParams.get("q") === "mashina")).toBe(true));
    fireEvent.change(screen.getByLabelText("Holat"), { target: { value: "loss" } });
    fireEvent.change(screen.getByLabelText("ABC"), { target: { value: "B" } });
    await waitFor(() => expect(skusUrls(api).some((u) => u.searchParams.get("label") === "loss" && u.searchParams.get("abc") === "B")).toBe(true));
    expect(history.location.search).toContain("label=loss");
  });

  it("filtr natijasi bo'sh — 'Hech narsa topilmadi' va tozalash tugmasi", async () => {
    const { history } = await renderAt(`${PATH}&q=yoq`, { [SKUS_ROUTE]: () => json(200, skusData({ items: [], total: 0 })) });
    expect(await screen.findByText("Hech narsa topilmadi")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Filtrlarni tozalash" }));
    await waitFor(() => expect(history.location.search).not.toContain("q="));
  });

  it("ro'yxat holati (qidiruv, filtr, saralash, sahifa) SKU havolasiga qo'shiladi; SKU sahifasidan 'qaytish' uni tiklaydi (B4.50)", async () => {
    const state = "q=mashina&sort=-units&label=loss&abc=B&page=2";
    const { history } = await renderAt(`${PATH}&${state}`, { [SKUS_ROUTE]: () => json(200, skusData({ total: 120, page: 2, pages: 3 })) });
    await screen.findByRole("table", { name: CAPTION });
    const link = within(table()).getByRole("link", { name: "Oʻyinchoq mashina qizil" });
    const href = new URL(link.getAttribute("href")!, "http://x");
    expect(href.pathname).toBe(`/products/${SKU_1}`);
    for (const [k, v] of new URLSearchParams(state)) expect(href.searchParams.get(k)).toBe(v);
    fireEvent.click(link);
    const back = await screen.findByRole("link", { name: /Mahsulotlarga qaytish/ });
    const to = new URL(back.getAttribute("href")!, "http://x");
    expect(to.pathname).toBe("/products");
    for (const [k, v] of new URLSearchParams(state)) expect(to.searchParams.get(k)).toBe(v);
    expect(history.location.pathname).toBe(`/products/${SKU_1}`);
    fireEvent.click(back);
    await waitFor(() => expect(history.location.pathname).toBe("/products"));
    expect(history.location.search).toContain("q=mashina");
    expect(history.location.search).toContain("page=2");
  });

  it("sahifalash: 20 tadan ko'p bo'lsa raqamlar, keyingi sahifa `page` bilan so'raladi va URL'ga yoziladi", async () => {
    const { api, history } = await renderAt(PATH, {
      [SKUS_ROUTE]: [
        () => json(200, skusData({ items: [skuRow()], total: 120, page: 1, pages: 3 })),
        () => json(200, skusData({ items: [SECOND], total: 120, page: 2, pages: 3 })),
      ],
    });
    await screen.findByRole("table", { name: CAPTION });
    expect(skusUrls(api)[0]!.searchParams.get("page")).toBe("1");
    expect(skusUrls(api)[0]!.searchParams.get("limit")).toBe("50");
    expect(screen.queryByRole("button", { name: "Yana yuklash" })).toBeNull();
    expect(screen.getByText(/1–50 \/ 120 ta/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "1-sahifa" }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(screen.getByRole("button", { name: "Keyingi sahifa" }));
    await waitFor(() => expect(skusUrls(api)[1]!.searchParams.get("page")).toBe("2"));
    expect(history.location.search).toContain("page=2");
    await waitFor(() => expect(within(table()).getByRole("link", { name: "Кружка белая" })).toBeTruthy());
    expect(screen.getByText(/51–100 \/ 120 ta/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "2-sahifa" }).getAttribute("aria-current")).toBe("page");
  });

  it("sahifa o'lchami tanlanadi va eslanadi; filtr o'zgarsa — 1-sahifa", async () => {
    const { api, history } = await renderAt(`${PATH}&page=2`, {
      [SKUS_ROUTE]: (r) => json(200, skusData({ items: [SECOND], total: 120, page: Number(new URL(r.url).searchParams.get("page")), pages: 3 })),
    });
    await screen.findByRole("table", { name: CAPTION });
    expect(skusUrls(api)[0]!.searchParams.get("page")).toBe("2");
    fireEvent.change(screen.getByLabelText("Sahifada"), { target: { value: "20" } });
    await waitFor(() => expect(skusUrls(api).some((u) => u.searchParams.get("limit") === "20" && u.searchParams.get("page") === "1")).toBe(true));
    expect(history.location.search).not.toContain("page=");
    expect(localStorage.getItem("sellermax.pageSize")).toBe("20");
    fireEvent.change(screen.getByLabelText("Holat"), { target: { value: "loss" } });
    await waitFor(() => expect(skusUrls(api).some((u) => u.searchParams.get("label") === "loss" && u.searchParams.get("page") === "1")).toBe(true));
  });

  it("URL'dagi sahifa oxirgisidan oshsa — API qaytargan sahifaga o'tadi", async () => {
    const { history } = await renderAt(`${PATH}&page=9`, { [SKUS_ROUTE]: () => json(200, skusData({ total: 60, page: 2, pages: 2 })) });
    await screen.findByRole("table", { name: CAPTION });
    await waitFor(() => expect(history.location.search).toContain("page=2"));
  });

  it("20 tadan kam — sahifalash chizilmaydi", async () => {
    await renderTable();
    expect(screen.queryByRole("navigation", { name: "Sahifalar" })).toBeNull();
    expect(screen.queryByLabelText("Sahifada")).toBeNull();
  });

  it("Dona, O'rtacha narx, Qoldiq, Holat (va ABC) ustunlarida '?' tushuntirish: F-raqam, formula, manba (B4.53)", async () => {
    localStorage.setItem(`up.products.columns.${ORG_ID}`, JSON.stringify([...DEFAULT_COLUMNS, "abc"]));
    await renderTable();
    for (const [name, code] of [["Dona", "F2"], ["Oʻrtacha narx", "F3"], ["Qoldiq", "F24"], ["Holat", "F12, F13"], ["ABC", "F28"]] as const) {
      const th = within(table()).getAllByRole("columnheader").find((h) => h.textContent?.startsWith(name));
      expect(th, name).toBeTruthy();
      const help = within(th!).getByRole("button", { name: /Qanday hisoblanadi/ });
      fireEvent.click(help);
      expect(await screen.findByText(new RegExp(`· ${code}$`)), name).toBeTruthy();
      fireEvent.keyDown(document.body, { key: "Escape" });
    }
  });

  it("'Jadvaldan tashqari' — filtr bo'lsa 'filtr bu qismlarga ta'sir qilmaydi' izohi (B4.53)", async () => {
    await renderTable();
    expect(screen.queryByText(/Qidiruv va filtr bu qismlarga/)).toBeNull();
    cleanup();
    await renderAt(`${PATH}&label=loss`, { [SKUS_ROUTE]: () => json(200, skusData()) });
    await screen.findByRole("table", { name: CAPTION });
    expect(screen.getByText(/Qidiruv va filtr bu qismlarga taʼsir qilmaydi/)).toBeTruthy();
  });

  it("jadvaldan tashqari: SKU'ga bog'lanmagan sotuvlar va taqsimlanmagan xarajat alohida", async () => {
    await renderTable();
    const block = screen.getByRole("region", { name: "Jadvaldan tashqari" });
    expect(within(block).getByText(/1 dona, tushum/)).toBeTruthy();
    expect(norm(within(block).getByText(/Sotuvsiz kunlar xarajati/).textContent!)).toContain(norm(f.money("-12000.00")));
    // B4.54: "sotuvsiz kunlar xarajati" nimaligi izohda tushuntiriladi.
    expect(within(block).getByText(/hech bir SKUʼga boʻlinmaydi, lekin jami sof foydadan ayriladi/)).toBeTruthy();
  });

  it("xato — qizil banner va 'Qayta urinish'; yuklanish — skelet", async () => {
    await renderAt(PATH, { [SKUS_ROUTE]: () => problem(500, "internal") });
    expect(await screen.findByRole("button", { name: "Qayta urinish" }, { timeout: 8000 })).toBeTruthy();
  }, 15_000);

  it("axe: jiddiy xato 0", async () => {
    await renderTable();
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  }, 30_000);
});

describe("ustunlar va ko'rinishlar", () => {
  it("ustun tanlash: ko'rsatiladi, brauzerda eslanadi; mahsulot ustuni o'chmaydi; standartga qaytish", async () => {
    await renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Ustunlar" }));
    const [group] = screen.getAllByRole("group", { name: "Ustunlar" }) as [HTMLElement];
    expect((within(group).getByLabelText("Mahsulot") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(within(group).getByLabelText("Komissiya"));
    expect(within(table()).getByRole("columnheader", { name: /^Komissiya/ })).toBeTruthy();
    expect(within(table()).getAllByText("20%")).toHaveLength(3); // komissiya (ikki qator) + birinchi qator margasi
    expect(JSON.parse(localStorage.getItem(`up.products.columns.${ORG_ID}`)!)).toContain("commission");
    fireEvent.click(within(group).getByLabelText("Tushum"));
    expect(within(table()).queryByRole("columnheader", { name: /^Tushum/ })).toBeNull();
    fireEvent.click(within(group).getByRole("button", { name: "Standart ustunlar" }));
    expect(within(table()).queryByRole("columnheader", { name: /^Komissiya/ })).toBeNull();
    expect(within(table()).getByRole("columnheader", { name: /^Tushum/ })).toBeTruthy();
  });

  it("saqlangan ustunlar keyingi ochilishda tiklanadi", async () => {
    localStorage.setItem(`up.products.columns.${ORG_ID}`, JSON.stringify(["product", "ads", "normative", "nonsense"])); // "normative" — olib tashlangan ustun (ADR-035)
    await renderTable();
    expect(headers().map((h) => h!.replace(/Qanday hisoblanadi.*$/, "").trim())).toEqual(["Mahsulot", "Reklama/dona"]);
  });

  it("ko'rinishni saqlash, qo'llash va o'chirish", async () => {
    const { history } = await renderAt(`${PATH}&label=loss&sort=-roi`);
    await screen.findByRole("table", { name: CAPTION });
    fireEvent.click(screen.getByRole("button", { name: "Koʻrinishlar" }));
    fireEvent.change(screen.getByPlaceholderText("Koʻrinish nomi"), { target: { value: "Zararlilar" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(JSON.parse(localStorage.getItem(`up.products.views.${ORG_ID}`)!)).toMatchObject([{ name: "Zararlilar", label: "loss", sort: "-roi" }]);
    // Filtrni tozalab, ko'rinishni qo'llaymiz.
    fireEvent.change(screen.getByLabelText("Holat"), { target: { value: "" } });
    await waitFor(() => expect(history.location.search).not.toContain("label="));
    fireEvent.click(screen.getByRole("button", { name: "Zararlilar" }));
    await waitFor(() => expect(history.location.search).toContain("label=loss"));
    fireEvent.click(screen.getByRole("button", { name: "Koʻrinishlar" }));
    fireEvent.click(screen.getByRole("button", { name: "“Zararlilar” koʻrinishini oʻchirish" }));
    expect(JSON.parse(localStorage.getItem(`up.products.views.${ORG_ID}`)!)).toEqual([]);
  });
});

describe("SKU sahifasi", () => {
  async function renderSku(routes: Routes = {}, role = "owner") {
    const out = await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`, routes, role);
    await screen.findByRole("heading", { level: 1, name: "Oʻyinchoq mashina qizil" });
    return out;
  }

  it("sarlavha, Uzum havolasi, KPI'lar, lotlar, qaytish sabablari, bog'langan tovar", async () => {
    const { api } = await renderSku();
    expect(api.count(skuRoute(SKU_1))).toBe(1);
    const link = screen.getByRole("link", { name: /Uzumʼda ochish/ });
    expect(link.getAttribute("href")).toBe("https://uzum.uz/ru/product/987654");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText("Foydali")).toBeTruthy();
    expect(screen.getByText("ABC: A")).toBeTruthy();
    expect(screen.getByText(norm(f.money("240000.00")))).toBeTruthy(); // sof foyda
    expect(screen.queryByText("Meʼyoriy foyda/dona")).toBeNull(); // bonus ko'rsatkichi yo'q (ADR-035)
    const lots = screen.getByRole("table", { name: "Tannarx tarixi (tovar partiyalari)" });
    expect(within(lots).getByText("Yoʻlda")).toBeTruthy();
    expect(within(lots).getByText("Markaziy bank kursi")).toBeTruthy();
    expect(within(lots).getByText(n("100000.000000").replace(/,\d+$/, ""))).toBeTruthy();
    const returns = screen.getByRole("table", { name: "Qaytishlar sabablari" });
    expect(within(returns).getByText("Defekt")).toBeTruthy();
    expect(within(returns).getByText("Sabab koʻrsatilmagan")).toBeTruthy();
    const linked = screen.getByRole("region", { hidden: true, name: "Tovar" }).textContent ?? "";
    expect(linked).toContain("Mashina");
    expect(screen.getByRole("link", { name: "Кружка белая" }).getAttribute("href")).toContain(`/products/${SKU_2}`);
    expect(screen.getAllByRole("img", { name: /Kunlik tushum va sof foyda/ }).length).toBeGreaterThan(0);
  });

  it("B4.45: 'Tannarx/dona' KPI jadval bilan bir xil — sotuvsiz SKU'da boshlang'ich narx izoh bilan; kalkulyator manbasi", async () => {
    const sku = skuRow({ units: 0, cogs_per_unit: null, unit_cost: "45000.00", unit_cost_source: "opening" });
    const calc = { ...skuDetail().calc, unit_cost: "45000.00", sources: { ...skuDetail().calc.sources, unit_cost: "opening" } };
    await renderSku({ [skuRoute(SKU_1)]: () => json(200, skuDetail({ sku, calc })) });
    const kpi = screen.getByText("Tannarx/dona", { selector: ".ui-kpi *" }).closest(".ui-kpi")!;
    expect(norm(kpi.textContent!)).toContain(norm(f.money("45000.00")));
    expect(kpi.textContent).toContain("(boshlangʻich)");
    expect(within(kpi as HTMLElement).getByRole("button", { name: /Qanday hisoblanadi/ })).toBeTruthy();
    expect(screen.getByText("Boshlangʻich holatdagi narx")).toBeTruthy(); // kalkulyator: tannarx manbasi
  });

  it("tovarsiz SKU: lotlar o'rniga ogohlantirish, 'Tovarga bog'lash' tugmasi", async () => {
    await renderSku({ [skuRoute(SKU_1)]: () => json(200, skuDetail({ linked: null, lots: [], sku: skuRow({ item_id: null }) })) });
    expect(screen.getByText(/SKU tovarga bogʻlanmagan, shuning uchun tannarx yoʻq/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tovarga bogʻlash" })).toBeTruthy();
  });

  it("topilmadi (404) — xato matni; ruxsatsiz roldagi odam bog'lash tugmasini ko'rmaydi", async () => {
    await renderAt(`/products/${SKU_1}`, { [skuRoute(SKU_1)]: () => problem(404, "sku_not_found") });
    expect(await screen.findByRole("alert")).toBeTruthy();
    cleanup();
    await renderSku({}, "accountant");
    expect(screen.queryByRole("button", { name: "Tovarni oʻzgartirish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Tovardan ajratish" })).toBeNull();
  }, 15_000);

  it("orqaga havola filtrlarni saqlaydi", async () => {
    await renderSku();
    expect(screen.getByRole("link", { name: /Mahsulotlarga qaytish/ }).getAttribute("href")).toBe("/products?from=2026-09-01&to=2026-10-31");
  });

  it("axe: jiddiy xato 0", async () => {
    await renderSku();
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  }, 30_000);
});

describe("unit kalkulyator", () => {
  const calls = (api: ReturnType<typeof mockApi>) =>
    api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === `/api/v1/orgs/${ORG_ID}/unit-calc`);

  async function renderCalc(routes: Routes = {}) {
    const out = await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`, routes);
    await screen.findByRole("heading", { name: "Unit kalkulyator" });
    return out;
  }

  it("boshlang'ich qiymatlar davr haqiqatidan (manbasi bilan), natija serverdan: foyda, zararsizlik narxi", async () => {
    const { api } = await renderCalc();
    expect(norm((screen.getByLabelText("Narx") as HTMLInputElement).value)).toBe("200 000,00");
    expect(screen.getByText("Oxirgi pullik logistika")).toBeTruthy();
    expect(screen.getByText("Davr haqiqiy komissiyasi")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("calc-profit").textContent).toBe(norm(f.money("43660.00")).replace(/ /g, " ")));
    expect(screen.getByTestId("calc-breakeven").textContent).toContain("141");
    const [first] = calls(api);
    expect(Object.fromEntries(first!.searchParams)).toEqual({
      price: "200000.00",
      unit_cost: "100000.00",
      logistics: "5000.00",
      packaging: "0",
      commission_pct: "20.00",
      tax_pct: "4.00",
      ads_pct: "1.67",
    });
  });

  it("narx o'zgarsa qayta so'raladi; maqsadli marja — narx; ulush 100% dan oshsa — 'hech qanday narx'", async () => {
    const { api } = await renderCalc({
      [UNIT_CALC_ROUTE]: (r) => {
        const q = new URL(r.url).searchParams;
        if (q.get("commission_pct") === "99") return json(200, unitCalc({ share_pct: "104.67", breakeven: null, target_price: null, profit: "-5000.00" }));
        return json(200, unitCalc({ target_price: q.get("target_margin_pct") ? "180000.00" : null }));
      },
    });
    await waitFor(() => expect(screen.getByTestId("calc-profit")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Narx"), { target: { value: "250000" } });
    await waitFor(() => expect(calls(api).some((u) => u.searchParams.get("price") === "250000")).toBe(true));
    fireEvent.change(screen.getByLabelText(/Maqsadli marja/), { target: { value: "20" } });
    await waitFor(() => expect(screen.getByTestId("calc-target").textContent).toContain("180"));
    expect(calls(api).some((u) => u.searchParams.get("target_margin_pct") === "20")).toBe(true);
    fireEvent.change(screen.getByLabelText("Komissiya"), { target: { value: "99" } });
    await waitFor(() => expect(screen.getByTestId("calc-breakeven").textContent).toBe("Hech qanday narx foyda bermaydi"));
    expect(screen.getByText(/narxni oshirish foydani oshirmaydi/)).toBeTruthy();
    // Boshlang'ich qiymatlarga qaytish.
    fireEvent.blur(screen.getByLabelText("Narx"));
    fireEvent.click(screen.getByRole("button", { name: "Boshlangʻich qiymatlar" }));
    expect(norm((screen.getByLabelText("Narx") as HTMLInputElement).value)).toBe("200 000,00");
  });

  it("kiritish o'zgarmasa qo'shimcha so'rov ketmaydi; tez yozish — bitta so'rov", async () => {
    const { api } = await renderCalc();
    await waitFor(() => expect(screen.getByTestId("calc-profit")).toBeTruthy());
    const before = calls(api).length;
    await new Promise((r) => setTimeout(r, 1000)); // debounce (300 ms) dan ancha uzoq
    expect(calls(api)).toHaveLength(before);
    const price = screen.getByLabelText("Narx");
    for (const v of ["2", "25", "250", "2500", "25000"]) fireEvent.change(price, { target: { value: v } });
    await waitFor(() => expect(calls(api).some((u) => u.searchParams.get("price") === "25000")).toBe(true));
    expect(calls(api).filter((u) => u.searchParams.get("price") !== "200000.00")).toHaveLength(1);
  });

  it("noto'g'ri qiymat (422) — aniq xato matni, eski natija ko'rsatilmaydi; to'g'rilansa natija qaytadi", async () => {
    await renderCalc({
      [UNIT_CALC_ROUTE]: (r) => {
        const q = new URL(r.url).searchParams;
        return Number(q.get("commission_pct")) > 100 ? problem(422, "validation_error") : json(200, unitCalc());
      },
    });
    await waitFor(() => expect(screen.getByTestId("calc-profit")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Komissiya"), { target: { value: "150" } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("foizlar 0 dan 100 gacha");
    expect(screen.queryByTestId("calc-profit")).toBeNull();
    fireEvent.change(screen.getByLabelText("Komissiya"), { target: { value: "20" } });
    await waitFor(() => expect(screen.getByTestId("calc-profit")).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("qiymat yo'q — taxmin yo'q: maydon bo'sh, so'rov ketmaydi, 'kiriting' tavsiyasi", async () => {
    const detail = skuDetail({ calc: { price: null, unit_cost: null, logistics: null, packaging: "0", commission_pct: null, tax_pct: null, ads_pct: null, sources: {} } });
    const { api } = await renderCalc({ [skuRoute(SKU_1)]: () => json(200, detail) });
    expect(screen.getByText("Narx, tannarx va komissiyani kiriting — natija shu yerda chiqadi.")).toBeTruthy();
    expect(screen.getAllByText("Qiymat topilmadi — kiriting").length).toBeGreaterThan(0);
    expect(calls(api)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Narx"), { target: { value: "100000" } });
    fireEvent.change(screen.getByLabelText("Tannarx/dona"), { target: { value: "40000" } });
    fireEvent.change(screen.getByLabelText("Komissiya"), { target: { value: "20" } });
    await waitFor(() => expect(calls(api)).toHaveLength(1));
    expect(Object.fromEntries(calls(api)[0]!.searchParams)).toMatchObject({ logistics: "0", tax_pct: "0", ads_pct: "0" });
  });
});

describe("SKU sahifasi grafigi (B4.53)", () => {
  it("sotuvsiz kunda xarajat bo'lsa izoh chiqadi; bo'lmasa — yo'q", async () => {
    await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`);
    await screen.findByRole("heading", { name: "Unit kalkulyator" });
    expect(screen.queryByText(/Sotuvsiz kunlarda faqat xarajat/)).toBeNull();
    cleanup();
    const detail = skuDetail();
    detail.history = [{ ...detail.history[0]!, net_profit: "-5000.00" }, ...detail.history.slice(1)];
    await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`, { [skuRoute(SKU_1)]: () => json(200, detail) });
    expect(await screen.findByText(/Sotuvsiz kunlarda faqat xarajat/)).toBeTruthy();
  });
});

describe("SKU sahifasi grafiklari (B4.56)", () => {
  const day = (d: string, over: Record<string, unknown> = {}) => ({ day: d, units: 0, revenue: "0.00", net_profit: "0.00", profit_per_unit: null, price: null, commission_pct: null, stock: null, ...over });

  it("narx va qoldiq TARIXI grafigi yo'q (ADR-055); hozirgi narx — KPI; kunlik tushum grafigi bor", async () => {
    const detail = skuDetail();
    detail.history = [day("2026-10-02", { units: 2, revenue: "400000.00", net_profit: "80000.00", price: "200000.00", stock: 8 }), day("2026-10-05", { price: "200000.00", stock: 7 })];
    await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`, { [skuRoute(SKU_1)]: () => json(200, detail) });
    await screen.findByRole("heading", { name: "Unit kalkulyator" });
    expect(screen.getByText("Kunlik tushum va sof foyda")).toBeTruthy();
    expect(screen.queryByText(/Narx tarixi/)).toBeNull();
    expect(screen.queryByText(/Qoldiq tarixi/)).toBeNull();
    expect(document.querySelectorAll(".chart-frame")).toHaveLength(1);
    // Hozirgi narx (Uzum katalogi) va qoldiq — KPI sifatida qoladi.
    expect(screen.getByText("Uzumdagi narx")).toBeTruthy();
    expect(screen.getByText("Qoldiq")).toBeTruthy();
  });

  it("KPI va nishonlarda '?' tushuntirish: Dona (F2), O'rtacha narx (F3), Holat, ABC", async () => {
    await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`);
    await screen.findByRole("heading", { name: "Unit kalkulyator" });
    for (const name of ["Dona", "Oʻrtacha narx", "Holat", "ABC"]) {
      expect(screen.getAllByRole("button", { name: new RegExp(`Qanday hisoblanadi: ${name}`) }).length, name).toBeGreaterThan(0);
    }
  });
});

describe("fillDays (B4.56)", () => {
  it("davrning hamma kuni: ma'lumotli kun saqlanadi, bo'shlari nol/bo'sh bilan to'ldiriladi", () => {
    const got = fillDays([{ day: "2026-10-02", units: 2, revenue: "5.00", net_profit: "1.00", profit_per_unit: "0.50", price: "9.00", commission_pct: null, stock: 3 }], "2026-10-01", "2026-10-04");
    expect(got.map((d) => d.day)).toEqual(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
    expect(got[1]!.units).toBe(2);
    expect(got[0]).toMatchObject({ units: 0, revenue: "0.00", net_profit: "0.00", price: null, stock: null });
    expect(fillDays([], "2026-10-05", "2026-10-05")).toHaveLength(1);
  });
});

describe("tovarga bog'lash", () => {
  async function open(routes: Routes = {}) {
    const out = await renderAt(`/products/${SKU_1}?from=2026-09-01&to=2026-10-31`, {
      [ITEMS_ROUTE]: () => json(200, { items: [{ id: ITEM_1, name: "Mashina", image_url: null, sku_count: 2 }, { id: "62222222-2222-4222-8222-222222222222", name: "Chiroq", image_url: null, sku_count: 1 }] }),
      [linkRoute(SKU_1)]: () => json(200, null),
      ...routes,
    });
    await screen.findByRole("button", { name: "Tovarni oʻzgartirish" });
    return out;
  }

  it("mavjud tovarga: tanlanadi, so'rov tanasi to'g'ri, hisobotlar qayta so'raladi", async () => {
    const { api } = await open();
    fireEvent.click(screen.getByRole("button", { name: "Tovarni oʻzgartirish" }));
    const dlg = await screen.findByRole("dialog", { name: "SKUʼni tovarga bogʻlash" });
    const input = within(dlg).getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "chiro" } });
    fireEvent.mouseDown(await within(dlg).findByRole("option", { name: /Chiroq/ }));
    fireEvent.click(within(dlg).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(linkRoute(SKU_1))).toEqual([{ mode: "existing", item_id: "62222222-2222-4222-8222-222222222222" }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(api.count(skuRoute(SKU_1))).toBe(2));
  });

  it("yangi tovar sifatida (nom SKU nomidan) va ajratish; xato — toast", async () => {
    const { api } = await open({ [linkRoute(SKU_1)]: [() => problem(404, "item_not_found"), () => json(200, null), () => json(200, null)] });
    fireEvent.click(screen.getByRole("button", { name: "Tovarni oʻzgartirish" }));
    const dlg = await screen.findByRole("dialog", { name: "SKUʼni tovarga bogʻlash" });
    fireEvent.click(within(dlg).getByLabelText("Yangi tovar sifatida"));
    expect((within(dlg).getByLabelText("Yangi tovar nomi") as HTMLInputElement).value).toBe("Oʻyinchoq mashina qizil");
    fireEvent.change(within(dlg).getByLabelText("Yangi tovar nomi"), { target: { value: "  Termos " } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(linkRoute(SKU_1))[0]).toEqual({ mode: "new", name: "Termos" }));
    expect(screen.getByRole("dialog")).toBeTruthy(); // xatoda dialog ochiq qoladi
    fireEvent.click(within(dlg).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Tovardan ajratish" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "SKUʼni tovardan ajratish?" })).getByRole("button", { name: "Ha, ajratish" }));
    await waitFor(() => expect(api.bodiesOf(linkRoute(SKU_1))[2]).toEqual({ mode: "none" }));
  });

  it("tovardan ajratish — tasdiq bilan: bekor qilinsa so'rov ketmaydi, tasdiqlansa ketadi (B4.52)", async () => {
    const { api } = await open();
    fireEvent.click(screen.getByRole("button", { name: "Tovardan ajratish" }));
    const dlg = await screen.findByRole("dialog", { name: "SKUʼni tovardan ajratish?" });
    expect(dlg.textContent).toContain("Oʻyinchoq mashina qizil");
    expect(dlg.textContent).toContain("tovarsiz qoladi");
    expect(api.bodiesOf(linkRoute(SKU_1))).toEqual([]); // hali so'rov ketmadi
    fireEvent.click(within(dlg).getByRole("button", { name: "Bekor qilish" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.bodiesOf(linkRoute(SKU_1))).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Tovardan ajratish" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Ha, ajratish" }));
    await waitFor(() => expect(api.bodiesOf(linkRoute(SKU_1))).toEqual([{ mode: "none" }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("tovar qidiruvi serverda: yozilgan matn `q` bilan so'raladi, jami ko'p bo'lsa 'aniqroq yozing' izohi, tanlangan nom saqlanadi", async () => {
    const many = Array.from({ length: 50 }, (_, n) => ({ id: `6${String(n).padStart(7, "0")}-2222-4222-8222-222222222222`, name: `Tovar ${n}`, image_url: null, sku_count: 1 }));
    const found = { id: "62222222-2222-4222-8222-222222222222", name: "Chiroq LED", image_url: null, sku_count: 1 };
    const { api } = await open({
      [ITEMS_ROUTE]: (r) => {
        const q = new URL(r.url).searchParams.get("q");
        return json(200, q ? { items: [found], total: 1 } : { items: many, total: 620 });
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tovarni oʻzgartirish" }));
    const dlg = await screen.findByRole("dialog", { name: "SKUʼni tovarga bogʻlash" });
    const input = within(dlg).getByRole("combobox");
    fireEvent.focus(input);
    expect(await within(dlg).findByText("Birinchi 50 ta koʻrsatildi, jami 620 ta — aniqroq yozing")).toBeTruthy();
    fireEvent.change(input, { target: { value: "chiroq" } });
    fireEvent.mouseDown(await within(dlg).findByRole("option", { name: /Chiroq LED/ }));
    const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname.endsWith("/items"));
    expect(urls.some((u) => u.searchParams.get("q") === "chiroq")).toBe(true);
    // Tanlangach qidiruv tozalanadi (ro'yxat qaytadi), lekin tanlangan nom maydonda qoladi.
    await waitFor(() => expect((input as HTMLInputElement).value).toBe("Chiroq LED"));
    fireEvent.click(within(dlg).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(linkRoute(SKU_1))).toEqual([{ mode: "existing", item_id: found.id }]));
  });
});
