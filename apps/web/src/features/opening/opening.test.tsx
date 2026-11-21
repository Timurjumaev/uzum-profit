// Boshlang'ich holat sahifasi (B4.12, F41): jadval, qamrov, saqlash tanasi, sana almashsa taklif so'rovi, o'chirish,
// faqat ko'rish (buxgalter), axe. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, ME, ME_ROUTE, mockApi, ORG_ID, type Routes } from "../../test/api";
import { openingData, openingRow } from "../../test/opening";

const ROUTE = `GET /api/v1/orgs/${ORG_ID}/opening`;
const PUT = `PUT /api/v1/orgs/${ORG_ID}/opening`;

const data = openingData;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage(routes: Routes = {}, role = "owner") {
  const api = mockApi({ [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }), [ROUTE]: () => json(200, data()), ...routes });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/opening"] }), "uz-Latn")} />);
  return api;
}

const norm = (text: string | null) => (text ?? "").replace(/[\u00A0\u202F]/g, " ");

describe("boshlang'ich holat", () => {
  it("jadval, qamrov va ogohlantirishlar; axe toza", async () => {
    renderPage();
    await screen.findByRole("heading", { level: 1, name: "Boshlangʻich holat" });
    expect(await screen.findByText("Soat")).toBeTruthy();
    expect(screen.getByText("Sumka")).toBeTruthy();
    expect(norm(document.body.textContent)).toContain("tushumning 25");
    expect(screen.getByText(/2 ta partiya boshlash sanasidan oldin/)).toBeTruthy();
    expect(screen.getByText("Boshlangʻich holat oʻrnatilmagan")).toBeTruthy();
    expect((screen.getByLabelText("Boshlash sanasi") as HTMLInputElement).value).toBe("2026-11-01");
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });

  it("sotuvi va qoldig'i yo'q SKU'lar ko'rsatilmagani yoziladi; yo'q bo'lsa — yozuv yo'q", async () => {
    renderPage({ [ROUTE]: () => json(200, data({ hidden: 42 })) });
    expect(await screen.findByText(/Sotuvi ham, qoldigʻi ham boʻlmagan 42 ta SKU koʻrsatilmadi/)).toBeTruthy();
    cleanup();
    renderPage();
    await screen.findByText("Soat");
    expect(screen.queryByText(/koʻrsatilmadi/)).toBeNull();
  });

  it("narx kiritilgan qatorlar yuboriladi; javob keshga", async () => {
    const api = renderPage({ [PUT]: () => json(200, data({ start_on: "2026-11-01", coverage: "0.7700" })) });
    await screen.findByText("Soat");
    const prices = screen.getAllByLabelText(/Tannarx \/ dona/);
    fireEvent.change(prices[0]!, { target: { value: "12000" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash va qayta hisoblash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    expect(api.bodiesOf(PUT)[0]).toEqual({ start_on: "2026-11-01", rows: [{ item_id: "item-1", uzum_qty: 120, own_qty: 0, prices: [{ valid_from: null, unit_cost: "12000" }] }] });
    // Natija sahifa tepasida: nechta turga narx, qamrov va keyingi qadam havolalari.
    expect(await screen.findByText("Saqlandi")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Foydani koʻrish" }).getAttribute("href")).toBe("/pnl");
    expect(screen.getByRole("link", { name: "Omborni koʻrish" }).getAttribute("href")).toBe("/inventory");
    await waitFor(() => expect(norm(document.body.textContent)).toContain("tushumning 77"));
  });

  it("sana almashsa — shu sana uchun taklif so'raladi; o'chirish", async () => {
    const api = renderPage({
      [ROUTE]: [() => json(200, data({ start_on: "2026-10-01", as_of: "2026-10-01" })), () => json(200, data({ start_on: "2026-10-01", as_of: "2026-09-01", stock_source: "none" }))],
      [PUT]: () => json(200, data()),
    });
    await screen.findByText("Soat");
    fireEvent.change(screen.getByLabelText("Boshlash sanasi"), { target: { value: "2026-09-01" } });
    expect(await screen.findByText(/qoldigʻi saqlanmagan/)).toBeTruthy();
    expect(api.fetch.mock.calls.some(([r]) => (r as Request).url.includes("start=2026-09-01"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toEqual([{ start_on: null, rows: [] }]));
  });

  it("\"Faqat narxsiz turlar\" filtri: narxi borlar yashiriladi; hammasida narx bo'lsa — filtr yo'q", async () => {
    renderPage({
      [ROUTE]: () =>
        json(200, data({ rows: [openingRow({ prices: [{ valid_from: null, unit_cost: "5000.00" }] }), openingRow({ item_id: "item-2", name: "Sumka", skus: ["Sumka-1"] })] })),
    });
    await screen.findByText("Sumka");
    expect(screen.getByText("Soat-qora")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Faqat narxsiz turlar (1)"));
    expect(screen.queryByText("Soat-qora")).toBeNull();
    expect(screen.getByText("Sumka-1")).toBeTruthy();
    cleanup();
    renderPage({ [ROUTE]: () => json(200, data({ rows: [openingRow({ prices: [{ valid_from: null, unit_cost: "5000.00" }] })] })) });
    await screen.findByText("Soat-qora");
    expect(screen.queryByLabelText(/Faqat narxsiz turlar/)).toBeNull();
  });

  it("buxgalter faqat ko'radi", async () => {
    renderPage({}, "accountant");
    await screen.findByText("Soat");
    expect(screen.queryByRole("button", { name: "Saqlash va qayta hisoblash" })).toBeNull();
    expect((screen.getByLabelText("Boshlash sanasi") as HTMLInputElement).disabled).toBe(true);
  });
});

describe("do'kon filtri", () => {
  it("tanlangan do'kon so'rovga va saqlashga uzatiladi; umumiy tovar belgisi; topbar'da davr yo'q", async () => {
    const shop = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const api = mockApi({
      [ME_ROUTE]: () => json(200, ME),
      [ROUTE]: () => json(200, data({ rows: [{ ...data().rows[0]!, shared: true }] })),
      [PUT]: () => json(200, data()),
    });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: [`/opening?shop=${shop}`] }), "uz-Latn")} />);
    expect(await screen.findByText(/Boshqa doʻkonda ham sotiladi/)).toBeTruthy();
    expect(api.fetch.mock.calls.some(([r]) => (r as Request).url.includes(`shop=${shop}`))).toBe(true);
    expect(screen.queryByRole("button", { name: /Solishtirish/ })).toBeNull();
    fireEvent.change(screen.getAllByLabelText(/Tannarx \/ dona/)[0]!, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash va qayta hisoblash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    const put = api.fetch.mock.calls.map(([r]) => r as Request).find((r) => r.method === "PUT")!;
    expect(new URL(put.url).searchParams.getAll("shop")).toEqual([shop]);
  });
});

describe("mahsulot turlari", () => {
  it("guruh narxi hamma turga tushadi, bittasini alohida o'zgartirsa bo'ladi", async () => {
    const v = (id: string, sku: string) => openingRow({ item_id: null, sku_id: id, name: "AirPods gʻilof", skus: [sku], product_id: "p1", product: "AirPods gʻilof", uzum_suggested: 3 });
    const api = mockApi({
      [ME_ROUTE]: () => json(200, ME),
      [ROUTE]: () => json(200, data({ rows: [v("v1", "ELONE-AIRGILOF-ВИШН-4"), v("v2", "ELONE-AIRGILOF-ПАСТ-4")] })),
      [PUT]: () => json(200, data()),
    });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/opening"] }), "uz-Latn")} />);
    expect(await screen.findByText("2 ta tur (rang, model, oʻlcham)")).toBeTruthy();
    expect(screen.getByText("ELONE-AIRGILOF-ВИШН-4")).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy(); // bitta mahsulot — bitta jadval
    // "Tannarx" sarlavhasidagi tugma → "Barcha turlar uchun qoʻllash" → ✓ (Uzum kabinetidagi kabi).
    fireEvent.click(screen.getByRole("button", { name: "Barcha turlar uchun narx: AirPods gʻilof" }));
    fireEvent.change(screen.getByLabelText("Barcha turlar uchun qoʻllash"), { target: { value: "15000" } });
    fireEvent.click(screen.getByRole("button", { name: "Qoʻllash" }));
    expect(screen.queryByLabelText("Barcha turlar uchun qoʻllash")).toBeNull(); // panel yopildi
    const prices = screen.getAllByLabelText(/^Tannarx \/ dona — ELONE/) as HTMLInputElement[];
    expect(prices.map((x) => x.value.replace(/\s/g, ""))).toEqual(["15000", "15000"]);
    fireEvent.change(prices[1]!, { target: { value: "17000" } });
    fireEvent.click(screen.getByRole("button", { name: "Saqlash va qayta hisoblash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    const body = api.bodiesOf(PUT)[0] as { rows: Array<{ sku_id: string; prices: Array<{ unit_cost: string }> }> };
    expect(body.rows.map((r) => [r.sku_id, r.prices[0]!.unit_cost])).toEqual([["v1", "15000"], ["v2", "17000"]]);
  });
});

describe("ixcham jadval", () => {
  it("odatda faqat Tur va Tannarx; Uzum qoldig'i — matn; o'z omborim — belgi bilan", async () => {
    renderPage();
    await screen.findByText("Soat");
    const headers = () => screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(new Set(headers())).toEqual(new Set(["Tur (SKU)", "Tannarx, soʻm"]));
    expect(screen.getByText("Uzumda: 120 dona")).toBeTruthy();
    expect(screen.queryByLabelText(/^Uzumda \(dona\)/)).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Oʻz omborimda ham tovar bor/ }));
    expect(headers()).toContain("Oʻz omborimda, dona");
    expect(screen.getAllByLabelText(/^Oʻz omborimda \(dona\)/)).toHaveLength(2);
  });

  it("Uzum qoldig'i noma'lum (o'tgan sana, snapshot yo'q) — kiritish ustuni chiqadi", async () => {
    renderPage({ [ROUTE]: () => json(200, data({ stock_source: "none", rows: data().rows.map((r) => ({ ...r, uzum_suggested: null })) })) });
    await screen.findByText("Soat");
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toContain("Uzumda, dona");
    expect(screen.getAllByLabelText(/^Uzumda \(dona\)/)).toHaveLength(2);
  });
});

describe("tannarxni Excel orqali kiritish (B7.1)", () => {
  const PREVIEW = `POST /api/v1/orgs/${ORG_ID}/opening/costs/preview`;
  const APPLY = `POST /api/v1/orgs/${ORG_ID}/opening/costs/apply`;
  const preview = (over: Record<string, unknown> = {}) => ({
    new: 1,
    changed: 1,
    same: 2,
    empty: 3,
    error_count: 1,
    errors: [{ row: 9, reason: "Tannarx: son emas" }],
    changes: [
      { key: "item:a", row: 2, name: "Soat", old: null, new: "12500.00" },
      { key: "item:b", row: 3, name: "Sumka", old: "8000.00", new: "9000.00" },
    ],
    ...over,
  });
  const xlsx = () => new File(["{}"], "tannarx.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

  it("fayl yuklanadi → ko'rib chiqish (yangi / ustidan yoziladi / xato) → tasdiqdan keyin saqlanadi", async () => {
    const api = renderPage({ [PREVIEW]: () => json(200, preview()), [APPLY]: () => json(200, { saved: 2, unchanged: 0 }) });
    await screen.findByRole("heading", { level: 1, name: "Boshlangʻich holat" });
    const input = await screen.findByLabelText("Excel fayl");
    fireEvent.change(input, { target: { files: [xlsx()] } });
    const dialog = await screen.findByRole("dialog", { name: "Yuklangan fayl: nima oʻzgaradi" });
    expect(norm(dialog.textContent)).toContain("Yangi: 1");
    expect(norm(dialog.textContent)).toContain("Ustidan yoziladi: 1");
    expect(norm(dialog.textContent)).toContain("Xato: 1");
    expect(norm(dialog.textContent)).toContain("Qator 9: Tannarx: son emas");
    expect(norm(dialog.textContent)).toContain("1 ta mavjud tannarx ustidan yoziladi");
    // Hech narsa tasdiqdan oldin saqlanmagan; fayl tanasi to'g'ridan-to'g'ri yuborilgan.
    expect(api.count(APPLY)).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Saqlash (2)" }));
    await waitFor(() => expect(api.count(APPLY)).toBe(1));
    expect(api.bodiesOf(APPLY)[0]).toEqual({ changes: [{ key: "item:a", unit_cost: "12500.00" }, { key: "item:b", unit_cost: "9000.00" }] });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Yuklangan fayl: nima oʻzgaradi" })).toBeNull());
  });

  it("o'zgarish yo'q — 'Saqlash' o'chiq; bekor qilish hech narsa saqlamaydi", async () => {
    const api = renderPage({ [PREVIEW]: () => json(200, preview({ new: 0, changed: 0, same: 5, error_count: 0, errors: [], changes: [] })) });
    fireEvent.change(await screen.findByLabelText("Excel fayl"), { target: { files: [xlsx()] } });
    const dialog = await screen.findByRole("dialog", { name: "Yuklangan fayl: nima oʻzgaradi" });
    expect(norm(dialog.textContent)).toContain("Hech narsa oʻzgarmaydi");
    expect((screen.getByRole("button", { name: "Saqlash (0)" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Bekor qilish" }));
    expect(api.count(APPLY)).toBe(0);
  });

  it("server xatosi (shablon emas) — toast; ruxsati yo'q rolda blok ko'rinmaydi", async () => {
    renderPage({ [PREVIEW]: () => json(422, { type: "about:blank", title: "x", status: 422, code: "bad_template", detail: "shablon emas" }) });
    fireEvent.change(await screen.findByLabelText("Excel fayl"), { target: { files: [xlsx()] } });
    expect(await screen.findByText(/shablon emas|Fayl shablonga mos emas/i)).toBeTruthy();
    cleanup();
    renderPage({}, "accountant");
    await screen.findByRole("heading", { level: 1, name: "Boshlangʻich holat" });
    await screen.findByText("Soat");
    expect(screen.queryByLabelText("Excel fayl")).toBeNull();
  });
});
