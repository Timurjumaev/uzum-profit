// Foyda va zarar sahifasi (M5, B4.2): hisob varag'i ustunlari, qamrov banneri, sharshara, F16, kesimlar
// (URL'dagi `view`), drill-down, holatlar va kirish imkoniyati. Butun ilova soxta API ustida — `test/api.ts`.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import { json, ME, ME_ROUTE, mockApi, PNL_ROUTE, pnlData, problem, SALES_ROUTE, SHOP_A, SHOP_B, SYNC_ROUTE, syncStatus, type Routes } from "../../test/api";
import { pnlStatement, skuColumns } from "../../test/pnl";

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
  it("sarlavha, qatorlar tartibi (yalpi foyda bilan) va ustunlar: joriy, tushumga nisbatan, oldingi, farq", async () => {
    await renderPnl();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`Foyda va zarar, ${f.period("2026-09-01", "2026-10-31")}`);
    expect(norm(screen.getByText(/^Oldingi davr:/).textContent!)).toBe(norm(`Oldingi davr: ${f.period("2026-07-02", "2026-08-31")}`));
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
    expect(within(ledger()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Qator", "Joriy davr", "Tushumga nisbatan", "Oldingi davr", "Farq"]);
    const revenue = within(row("Tushum")).getAllByRole("cell").map((c) => norm(c.textContent ?? ""));
    expect(revenue).toEqual([n("10000000.00"), norm(f.percent("1.000000")), n("8000000.00"), n("2000000.00"), norm(f.change("0.250000"))]);
    expect(row("Yalpi foyda").className).toContain("is-subtotal");
    expect(row("Sof foyda").className).toContain("is-total");
    // O'ylab topilgan qator yo'q: Uzum xarajatlari API bergandek (ADR-035).
    expect(screen.queryByText(/Standart tarif/)).toBeNull();
    // Tannarxsiz to'lov — ayiriluvchi (zanjir to'g'ri chiqsin).
    expect(within(row("Tannarxsiz sotuvlar")).getByText(n("-750000.00"))).toBeTruthy();
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

  it("F16: kutilayotgan foyda; R hisoblanmasa sababi va koeffitsientsiz summa; do'konlar bo'yicha", async () => {
    await renderPnl();
    const [block] = screen.getAllByRole("region", { name: /Kutilayotgan/ }); // blok (ichida do'konlar jadvali)
    expect(norm(within(block!).getByTestId("pending-amount").textContent!)).toBe(m("870000.00"));
    expect(within(block!).getByText(/Realizatsiya darajasi hisoblanmadi/)).toBeTruthy();
    expect(within(block!).getByText(/2 ta sotuv tannarxsiz/)).toBeTruthy();
    const shops = within(block!).getByRole("table");
    expect(within(shops).getByText("Durii")).toBeTruthy(); // taxallus (alias)
    expect(within(shops).getByText("EL-ONE")).toBeTruthy();
    expect(within(shops).getByText(norm(f.percent("0.870000")))).toBeTruthy();
  });

  it("Jarayondagi sotuv yo'q — bo'sh matn", async () => {
    await renderPnl(PATH, { [PNL_ROUTE]: () => json(200, pnlData({ pending_shops: [], pending: { amount: "0.00", rate: null, raw: "0.00", uncovered_lines: 0 } })) });
    expect(screen.getByText("Bu davrda Jarayondagi sotuv yoʻq.")).toBeTruthy();
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
  it("Tushum: sotuv qatorlari so'raladi; Yalpi foyda — hisoblanadi, faqat formula (F8)", async () => {
    const { api } = await renderPnl(PATH, {
      [SALES_ROUTE]: () => json(200, { meta: pnlData().meta, items: [], next_cursor: null, summary: { units: 0, canceled: 0, returns: 0, cancel_share: null, return_share: null } }),
    });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Tushum" }));
    const dlg = await screen.findByRole("dialog", { name: "Tushum" });
    expect(within(dlg).getByText(m("10000000.00"), { selector: ".kpi" })).toBeTruthy();
    await waitFor(() => expect(api.count(SALES_ROUTE)).toBe(1));
    fireEvent.keyDown(dlg, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(within(ledger()).getByRole("button", { name: "Yalpi foyda" }));
    const gross = await screen.findByRole("dialog", { name: "Yalpi foyda" });
    expect(within(gross).getByText(/F8: Uzum toʻlovi − tannarx/)).toBeTruthy();
    expect(api.count(SALES_ROUTE)).toBe(1);
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
