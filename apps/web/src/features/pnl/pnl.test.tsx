// Foyda va zarar sahifasi (M5, ADR-037): hisob varag'i ustunlari (naqd, kutilayotgan, jami + solishtirish), qamrov
// banneri, sharshara, kutilayotgan sof foyda (F16), kesimlar (URL'dagi `view`), drill-down, holatlar va kirish
// imkoniyati. Butun ilova soxta API ustida — `test/api.ts`.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { EXPENSES_ROUTE, json, ME, ME_ROUTE, mockApi, PNL_ROUTE, pnlData, problem, SALES_ROUTE, SHOP_A, SHOP_B, SYNC_ROUTE, syncStatus, type Routes } from "../../test/api";
import { expectedPart, pnlStatement, skuColumns } from "../../test/pnl";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const m = (value: string) => norm(f.money(value));
const n = (value: string) => norm(f.money(value, { unit: false }));
const PATH = "/pnl?from=2026-09-01&to=2026-10-31";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function renderPnl(path = PATH, routes: Routes = {}, lang: "uz-Latn" | "ru" = "uz-Latn") {
  const api = mockApi({ [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: lang } }), ...routes });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, lang)} />);
  await screen.findByRole("table", { name: lang === "ru" ? "Прибыль и убыток: от выручки до чистой прибыли" : "Foyda va zarar: tushumdan sof foydagacha" });
  return { api, history };
}

const ledger = () => screen.getByRole("table", { name: "Foyda va zarar: tushumdan sof foydagacha" });
const row = (name: string) => within(ledger()).getByRole("row", { name: new RegExp(`^${name}`) });
const pnlUrls = (api: ReturnType<typeof mockApi>) =>
  api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === PNL_ROUTE.split(" ")[1]);

describe("hisob varag'i", () => {
  it("sarlavha, qatorlar tartibi (yalpi foyda bilan) va ustunlar: naqd, kutilayotgan, jami, tushumga nisbatan, oldingi, farq", async () => {
    await renderPnl();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`Foyda va zarar, ${f.period("2026-09-01", "2026-10-31")}`);
    expect(norm(screen.getByText(/^Oldingi davr:/).textContent!)).toBe(norm(`Oldingi davr: ${f.period("2026-07-02", "2026-08-31")}`));
    expect(screen.getByText(/^Naqd — yakunlangan sotuvlar/)).toBeTruthy();
    const names = within(ledger())
      .getAllByRole("rowheader")
      .map((h) => h.querySelector(".ui-ledger__link")?.textContent ?? h.textContent);
    expect(names).toEqual([
      "Tushum",
      "Uzum komissiyasi",
      "Logistika",
      "Uzum toʻlovi",
      "Tannarxsiz sotuvlar toʻlovi (hisobga kirmadi)",
      "Tannarx",
      "Yalpi foyda",
      "Reklama",
      "Kompensatsiya",
      "ijara",
      "Soliq",
      "Tannarxsiz qismga toʻgʻri kelgan xarajat",
      "Sof foyda",
    ]);
    expect(within(ledger()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Qator",
      "Naqd",
      "Kutilayotgan",
      "Jami",
      "Tushumga nisbatan",
      "Oldingi davr",
      "Farq",
    ]);
    const revenue = within(row("Tushum")).getAllByRole("cell").map((c) => norm(c.textContent ?? ""));
    expect(revenue).toEqual([
      n("8800000.00"),
      n("1200000.00"),
      n("10000000.00"),
      norm(f.percent("1.000000")),
      n("8000000.00"),
      n("2000000.00"),
      norm(f.change("0.250000")),
    ]);
    // ADR-037: sof foyda = naqd + kutilayotgan (API qatoridan).
    const net = within(row("Sof foyda")).getAllByRole("cell").map((c) => norm(c.textContent ?? ""));
    expect(net.slice(0, 3)).toEqual([n("3020000.00"), n("190000.00"), n("3210000.00")]);
    expect(row("Yalpi foyda").className).toContain("is-subtotal");
    expect(row("Sof foyda").className).toContain("is-total");
    // O'ylab topilgan qator yo'q: Uzum xarajatlari API bergandek (ADR-035).
    expect(screen.queryByText(/Standart tarif/)).toBeNull();
    // Tannarxsiz to'lov — ayiriluvchi (zanjir to'g'ri chiqsin), qismlari ham.
    expect(within(row("Tannarxsiz sotuvlar")).getByText(n("-750000.00"))).toBeTruthy();
    expect(within(row("Tannarxsiz sotuvlar")).getByText(n("-300000.00"))).toBeTruthy();
  });

  it("kutilayotgan logistika taxmini: '≈' belgisi va izoh (tamoyil 9); tarif noma'lum — alohida izoh", async () => {
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, pnlData({ statement: pnlStatement({ logistics_missing_lines: 2 }) })) });
    const marks = within(row("Logistika")).getAllByTitle("Taxminiy qismi bor");
    expect(marks).toHaveLength(2); // kutilayotgan va jami ustunida
    expect(within(row("Tushum")).queryByTitle("Taxminiy qismi bor")).toBeNull();
    expect(norm(screen.getByText(/^≈ Kutilayotgan logistikaning/).textContent!)).toContain(`${m("40000.00")} qismi (4 dona) taxminiy`);
    expect(screen.getByText("2 ta sotuvda logistika tarifi nomaʼlum — taxmin qoʻshilmadi.")).toBeTruthy();
  });

  it("tor ekran uchun ustun tanlash: 'Jami' standart, tanlansa jadval belgisi o'zgaradi", async () => {
    await renderPnl();
    expect(ledger().getAttribute("data-part")).toBe("total");
    const group = screen.getByRole("group", { name: "Hisob varagʻi ustuni" });
    expect(within(group).getAllByRole("radio").map((r) => r.closest("label")!.textContent)).toEqual(["Naqd", "Kutilayotgan", "Jami"]);
    fireEvent.click(within(group).getByRole("radio", { name: "Kutilayotgan" }));
    expect(ledger().getAttribute("data-part")).toBe("processing");
  });

  it("tannarx qamrovi < 100%: sariq banner — N ta sotuv (X so'm), 'Tannarx kiritish' filtrlar bilan", async () => {
    await renderPnl();
    const banner = screen.getByText(/tannarxsiz — foydaga kirmadi/).closest(".ui-banner")!;
    expect(banner.className).toContain("ui-tone--warning");
    expect(norm(screen.getByText(/tannarxsiz — foydaga kirmadi/).textContent!)).toBe(norm(`4 ta sotuv (${f.money("1000000.00")}) tannarxsiz — foydaga kirmadi.`));
    expect(screen.getByRole("link", { name: "Tannarx kiritish" }).getAttribute("href")).toBe("/products?from=2026-09-01&to=2026-10-31");
  });

  it("qamrov 100% — banner yo'q; qayta hisoblangan sotuvlar — ma'lumot banneri", async () => {
    const full = pnlStatement({ uncovered: { lines: 0, revenue: "0.00", payout: "0.00", expenses: "0.00", share: "0.000000" } });
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, pnlData({ statement: full, recalculated: 3 })) });
    expect(screen.queryByText(/tannarxsiz — foydaga kirmadi/)).toBeNull();
    expect(screen.getByText(/3 ta sotuvning tannarxi oxirgi 7 kunda qayta hisoblandi/)).toBeTruthy();
  });
});

describe("sharshara va kutilayotgan", () => {
  it("sharshara: tushumdan sof foydagacha, jadval ko'rinishida qadamlar", async () => {
    await renderPnl();
    const chart = await screen.findByRole("img", { name: /Tushumdan sof foydagacha/ });
    expect(chart.getAttribute("aria-label")).toContain("Sof foyda");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    const table = await screen.findByRole("table", { name: /Tushumdan sof foydagacha/ });
    const steps = within(table).getAllByRole("rowheader").map((h) => h.textContent);
    expect(steps).toEqual(["Tushum", "Komissiya", "Logistika", "Uzum toʻlovi", "Tannarxsiz", "Tannarx", "Yalpi foyda", "Uzum xarajatlari", "Oʻz xarajatlarim", "Soliq", "Tannarxsiz qism xarajati", "Sof foyda"]);
  });

  it("F16 (ADR-037): kutilayotgan sof foyda — dona, tushum, R fakt sifatida, taxminiy logistika, tannarxsiz; do'konlar", async () => {
    await renderPnl();
    const [block] = screen.getAllByRole("region", { name: /Kutilayotgan sof foyda/ }); // blok (ichida do'konlar jadvali)
    expect(norm(within(block!).getByTestId("expected-amount").textContent!)).toBe(m("190000.00"));
    expect(norm(within(block!).getByText(/^8 dona, tushum/).textContent!)).toContain(m("1200000.00"));
    expect(norm(within(block!).getByText(/bunday sotuvlarning/).textContent!)).toContain(norm(f.percent("0.850000")));
    expect(norm(within(block!).getByText(/^Logistika 4 dona uchun taxminiy/).textContent!)).toContain(m("40000.00"));
    expect(within(block!).getByText(/2 ta sotuvning tannarxi yoʻq/)).toBeTruthy();
    const shops = within(block!).getByRole("table");
    expect(within(shops).getByText("Durii")).toBeTruthy(); // taxallus (alias)
    expect(within(shops).getByText("EL-ONE")).toBeTruthy();
    expect(within(shops).getByText(n("160000.00"))).toBeTruthy();
    expect(within(shops).getByText(norm(f.percent("0.870000")))).toBeTruthy();
  });

  it("Jarayondagi sotuv yo'q — bo'sh matn; R yo'q — ma'lumot kam", async () => {
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, pnlData({ expected_shops: [], expected: expectedPart({ units: 0, lines: 0 }) })) });
    expect(screen.getByText("Bu davrda jarayondagi sotuv yoʻq.")).toBeTruthy();
    cleanup();
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, pnlData({ expected: expectedPart({ rate: null }) })) });
    expect(screen.getByText("Oxirgi 90 kunda yakunlanish ulushi uchun maʼlumot kam.")).toBeTruthy();
  });
});

describe("kesimlar", () => {
  it("standart — oylar (view=month so'raladi): ustun = oy + jami; filtrlar API'ga", async () => {
    const { api } = await renderPnl(`${PATH}&shop=${SHOP_A}`);
    const [call] = pnlUrls(api);
    expect(call!.searchParams.get("view")).toBe("month");
    expect(call!.searchParams.get("start")).toBe("2026-09-01");
    expect(call!.searchParams.getAll("shop")).toEqual([SHOP_A]);
    const table = screen.getByRole("table", { name: "Oylar" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Qator", f.month("2026-09-01"), f.month("2026-10-01"), "Jami"]);
    const revenue = within(table).getByRole("row", { name: /Tushum/ });
    expect(within(revenue).getAllByRole("cell").map((c) => norm(c.textContent!))).toEqual([n("4000000.00"), n("6000000.00"), n("10000000.00")]);
    expect(within(table).queryByText(/toʻgʻridan-toʻgʻri/)).toBeNull();
    // ADR-037: sof foyda ostida naqd va kutilayotgan qismlari, har oyda.
    const expected = within(table).getByRole("row", { name: /shundan kutilayotgan/ });
    expect(expected.className).toContain("is-part");
    expect(within(expected).getAllByRole("cell").map((c) => norm(c.textContent!))).toEqual([n("0.00"), n("190000.00"), n("190000.00")]);
    expect(within(table).getByRole("row", { name: /shundan naqd/ })).toBeTruthy();
  });

  it("do'konlar: URL'da view=shop, do'kon nomlari, to'g'ridan-to'g'ri / taqsimlangan qatorlar, taqsimlanmagan ustun", async () => {
    const columns = [
      { key: SHOP_A, statement: pnlStatement(), title: null, shop_id: null },
      { key: SHOP_B, statement: pnlStatement(), title: null, shop_id: null },
      { key: null, statement: pnlStatement({ revenue: "0.00" }), title: null, shop_id: null },
    ];
    const { api, history } = await renderPnl(PATH, {
      [PNL_ROUTE]: (r) => json(200, pnlData(new URL(r.url).searchParams.get("view") === "shop" ? { columns } : {})),
    });
    fireEvent.click(screen.getByRole("tab", { name: "Doʻkonlar" }));
    const table = await screen.findByRole("table", { name: "Doʻkonlar" });
    expect(history.location.search).toContain("view=shop");
    expect(pnlUrls(api).at(-1)!.searchParams.get("view")).toBe("shop");
    await waitFor(() => expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Qator", "Durii", "EL-ONE", "Taqsimlanmagan", "Jami"]));
    const direct = within(table).getByRole("row", { name: /Uzum xarajatlari — toʻgʻridan-toʻgʻri/ });
    expect(direct.className).toContain("is-part");
    expect(norm(within(direct).getAllByRole("cell")[0]!.textContent!)).toBe(n("-250000.00"));
    expect(within(table).getByRole("row", { name: /Oʻz xarajatlarim — taqsimlangan/ })).toBeTruthy();
    expect(screen.getByText(/Sotuvsiz kun xarajati/)).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Doʻkonlar" }).getAttribute("aria-selected")).toBe("true");
  });

  it("SKU: havoladan ochiladi; sof foyda bo'yicha, bog'lanmagan va taqsimlanmagan oxirida, jami qatori", async () => {
    await renderPnl(`${PATH}&view=sku`, { [PNL_ROUTE]: () => json(200, pnlData({ columns: skuColumns() })) });
    const table = await screen.findByRole("table", { name: "SKU" });
    const names = within(table).getAllByRole("rowheader").map((h) => h.textContent);
    expect(names).toEqual(["Sumka qora M", "Kamar L", "SKU bogʻlanmagan sotuvlar", "Taqsimlanmagan", "Jami"]);
    const loss = within(table).getByRole("row", { name: /Kamar L/ });
    expect(within(loss).getByText(n("-90000.00")).className).toContain("ui-text--negative");
    expect(within(table).getByRole("columnheader", { name: "shundan kutilayotgan" })).toBeTruthy();
    expect(screen.getByText("4 / 4 ta SKU (sof foyda boʻyicha)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Yana koʻrsatish" })).toBeNull();
  });

  it("SKU ko'p bo'lsa — 50 tadan, 'Yana ko'rsatish'", async () => {
    const many = Array.from({ length: 60 }, (_, i) => ({ key: `s${i}`, statement: pnlStatement({ net_profit: `${1000 + i}.00` }), title: `SKU ${i}`, shop_id: SHOP_A }));
    await renderPnl(`${PATH}&view=sku`, { [PNL_ROUTE]: () => json(200, pnlData({ columns: many })) });
    const table = await screen.findByRole("table", { name: "SKU" });
    expect(within(table).getAllByRole("rowheader")).toHaveLength(51); // 50 + jami
    fireEvent.click(screen.getByRole("button", { name: "Yana koʻrsatish" }));
    expect(within(table).getAllByRole("rowheader")).toHaveLength(61);
  });

  it("noto'g'ri view — oylar", async () => {
    const { api } = await renderPnl(`${PATH}&view=evil`);
    expect(pnlUrls(api)[0]!.searchParams.get("view")).toBe("month");
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
    logistics_estimated: null,
    payout: "150000.00",
    cogs: "80000.00",
    gross_profit: "70000.00",
    cost_flags: [],
    recalculated_at: null,
    previous_cogs: null,
    ...over,
  });
  const page = (items: unknown[], next: string | null) => ({
    meta: pnlData().meta,
    items,
    next_cursor: next,
    summary: { units: 2, canceled: 0, returns: 0, cancel_share: null, return_share: null },
  });
  const salesUrls = (api: ReturnType<typeof mockApi>) =>
    api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === SALES_ROUTE.split(" ")[1]);

  it("Tushum: yakunlangan va jarayondagi sotuv qatorlari, jami API qatoridan, kursor bilan 'Yana yuklash'", async () => {
    const { api } = await renderPnl(PATH, {
      [SALES_ROUTE]: [
        () => json(200, page([sale("s1", { status: "PROCESSING", group: "processing" }), sale("s2", { sku_id: null, sku_title: null, day: "2026-10-11" })], "c2")),
        () => json(200, page([sale("s3", { day: "2026-10-10" })], null)),
      ],
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Tushum" }));
    const dlg = await screen.findByRole("dialog", { name: "Tushum" });
    expect(within(dlg).getByText(m("10000000.00"), { selector: ".kpi" })).toBeTruthy(); // jami — hisob varag'idagi qator
    expect(await within(dlg).findByText("Sumka qora M")).toBeTruthy();
    expect(within(dlg).getByText("SKU bogʻlanmagan")).toBeTruthy();
    expect(within(dlg).getAllByText("Jarayonda")).toHaveLength(1); // Jarayondagi qator belgilanadi (ADR-036)
    expect(within(dlg).getAllByText(n("200000.00"), { selector: "td" })).toHaveLength(2);
    const [first] = salesUrls(api);
    expect(first!.searchParams.get("counted")).toBe("true"); // Yakunlangan + Jarayonda (ADR-036)
    expect(first!.searchParams.get("group")).toBeNull();
    expect(first!.searchParams.get("start")).toBe("2026-09-01");
    expect(first!.searchParams.get("end")).toBe("2026-10-31");
    fireEvent.click(within(dlg).getByRole("button", { name: "Yana yuklash" }));
    await waitFor(() => expect(within(dlg).getAllByRole("row")).toHaveLength(4)); // sarlavha + 3
    expect(salesUrls(api)[1]!.searchParams.get("cursor")).toBe("c2");
    expect(within(dlg).queryByRole("button", { name: "Yana yuklash" })).toBeNull();
  });

  it("Tannarx: taxminiy belgi (F22); Logistika: Uzum hali yozmagan — taxminiy belgi (ADR-037)", async () => {
    await renderPnl(PATH, {
      [SALES_ROUTE]: () =>
        json(200, page([sale("s1", { cost_flags: ["estimated"] }), sale("s2", { cogs: null, status: "PROCESSING", group: "processing", logistics_estimated: "10000.00" })], null)),
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Tannarx" }));
    const dlg = await screen.findByRole("dialog", { name: "Tannarx" });
    expect(await within(dlg).findAllByText("Taxminiy", { selector: ".ui-badge" })).toHaveLength(1);
    expect(within(dlg).getByRole("columnheader", { name: "Tannarx" })).toBeTruthy();
    expect(within(dlg).getByText(n("80000.00"))).toBeTruthy();
    fireEvent.keyDown(dlg, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(within(ledger()).getByRole("button", { name: "Logistika" }));
    const logistics = await screen.findByRole("dialog", { name: "Logistika" });
    expect(await within(logistics).findAllByText("Taxminiy", { selector: ".ui-badge" })).toHaveLength(1); // faqat s2
  });

  it("Uzum toifasi: shu toifa xarajatlari (chiqim — minus), toifa so'rovda", async () => {
    const expense = (id: string, type: string, amount: string) => ({
      id, shop_id: SHOP_A, external_id: 1, created_on: "2026-10-05T10:00:00Z", day: "2026-10-05", code: "Y1", raw_code: "Y1",
      category: "advertising", type, amount, name: "Reklama kampaniyasi", status: null, excluded: null, in_pnl: true, order_id: null, sale_item_id: null,
    });
    const { api } = await renderPnl(PATH, {
      [EXPENSES_ROUTE]: () =>
        json(200, {
          meta: pnlData().meta, uzum: [], uzum_total: "0.00", by_month: [], fines: [], own: [], own_total: "0.00", own_items: [],
          items: [expense("e1", "OUTCOME", "300000.00"), expense("e2", "INCOME", "50000.00")], next_cursor: null,
        }),
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Reklama" }));
    const dlg = await screen.findByRole("dialog", { name: "Reklama" });
    expect(await within(dlg).findAllByText("Reklama kampaniyasi")).toHaveLength(2);
    expect(within(dlg).getByText(n("-300000.00"))).toBeTruthy();
    expect(within(dlg).getByText(n("50000.00"))).toBeTruthy();
    const urls = api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === EXPENSES_ROUTE.split(" ")[1]);
    expect(urls[0]!.searchParams.get("category")).toBe("advertising");
  });

  it("hisoblanadigan qatorlar (Yalpi foyda, Soliq): yozuv yo'q, faqat formula; sotuv so'ralmaydi", async () => {
    const { api } = await renderPnl();
    fireEvent.click(within(ledger()).getByRole("button", { name: "Yalpi foyda" }));
    const gross = await screen.findByRole("dialog", { name: "Yalpi foyda" });
    expect(within(gross).getByText(/F8: Uzum toʻlovi − tannarx/)).toBeTruthy();
    fireEvent.keyDown(gross, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(within(ledger()).getByRole("button", { name: "Soliq" }));
    const tax = await screen.findByRole("dialog", { name: "Soliq" });
    expect(within(tax).getByText(/Bu qator boshqa qatorlardan hisoblanadi/)).toBeTruthy();
    expect(within(tax).getByText(/F11: Soliq profili boʻyicha/)).toBeTruthy();
    expect(api.count(SALES_ROUTE)).toBe(0);
  });

  it("ruxsat yo'q (xarajatlar sozlama ruxsati) — drawer ichida xato matni; Esc yopadi", async () => {
    await renderPnl(PATH, { [EXPENSES_ROUTE]: () => problem(403, "forbidden") });
    fireEvent.click(within(ledger()).getByRole("button", { name: "ijara" }));
    const dlg = await screen.findByRole("dialog", { name: "ijara" });
    expect((await within(dlg).findByRole("alert")).textContent).toContain("Bu sahifaga ruxsatingiz yoʻq.");
    fireEvent.keyDown(dlg, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("holatlar", () => {
  const empty = () =>
    pnlData({
      statement: pnlStatement({ lines: 0, revenue: "0.00", uncovered: { lines: 0, revenue: "0.00", payout: "0.00", expenses: "0.00", share: "0.000000" } }),
      columns: [],
    });

  it("sotuv yo'q + sinxron muammoli — 'yo'q' deyilmaydi (tamoyil 8); kesim — bo'sh matn", async () => {
    const broken = syncStatus({ healthy: false, freshness: { orders: new Date(Date.now() - 3 * 3600_000).toISOString(), expenses: null, products: null, returns: null } });
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, empty()), [SYNC_ROUTE]: () => json(200, broken) });
    expect(await screen.findByText("Maʼlumot toʻliq emas")).toBeTruthy();
    expect(screen.queryByText("Bu davrda sotuv yoʻq")).toBeNull();
    expect(screen.getByText("Bu davrda maʼlumot yoʻq.")).toBeTruthy();
  });

  it("server xatosi — sabab va 'Qayta urinish'", async () => {
    const api = mockApi({ [PNL_ROUTE]: () => problem(500, "internal") });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: [PATH] }), "uz-Latn")} />);
    const retry = await screen.findByRole("button", { name: "Qayta urinish" }, { timeout: 5000 });
    expect(retry).toBeTruthy();
    expect(api.count(PNL_ROUTE)).toBeGreaterThan(0);
  });

  it("o'tgan yil bilan solishtirish — hozircha oldingi davr ekani aytiladi", async () => {
    await renderPnl(`${PATH}&cmp=lastYear`);
    expect(screen.getByText(/Oʻtgan yil bilan solishtirish keyinroq/)).toBeTruthy();
  });

  it("ruscha: sarlavha va ustunlar", async () => {
    await renderPnl(PATH, {}, "ru");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Прибыль и убыток");
    const heads = within(screen.getByRole("table", { name: "Прибыль и убыток: от выручки до чистой прибыли" })).getAllByRole("columnheader");
    expect(heads.slice(1, 4).map((h) => h.textContent)).toEqual(["Факт", "Ожидается", "Итого"]);
    expect(screen.getByRole("tab", { name: "Магазины" })).toBeTruthy();
  });
});

describe("kirish imkoniyati", () => {
  it("axe-core: jiddiy xato 0 (oylar va SKU kesimi, drawer ochiq ham)", async () => {
    await renderPnl(PATH, { [PNL_ROUTE]: (r) => json(200, pnlData(new URL(r.url).searchParams.get("view") === "sku" ? { columns: skuColumns() } : {})) });
    const run = async () => {
      const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
      return result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((x) => x.target.join(" ")).join(", ")}`);
    };
    expect(await run()).toEqual([]);
    fireEvent.click(screen.getByRole("tab", { name: "SKU" }));
    await screen.findByRole("table", { name: "SKU" });
    expect(await run()).toEqual([]);
    fireEvent.click(within(ledger()).getByRole("button", { name: "Soliq" }));
    await screen.findByRole("dialog", { name: "Soliq" });
    expect(await run()).toEqual([]);
  }, 30_000);
});
