// "Maʼlumotlar holati" (M3): har do'kon × ma'lumot turi, akkaunt va kvota, uzilish, "Hozir yangilash".
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import type { components } from "../../lib/api/schema";
import { formatterFor } from "../../lib/format";
import { json, mockApi, problem, REFRESH_ROUTE, SYNC_ROUTE, syncStatus, type Routes } from "../../test/api";

const f = formatterFor("uz-Latn");
type Kind = components["schemas"]["KindStatus"];
const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const kind = (over: Partial<Kind> & { kind: string }): Kind => ({
  last_success_at: minutesAgo(3),
  last_attempt_at: minutesAgo(3),
  status: "ok",
  mode: "incremental",
  started_at: null,
  finished_at: null,
  fetched: 120,
  written: 120,
  total: null,
  error: null,
  http_status: null,
  ...over,
});

function status(over: Partial<components["schemas"]["SyncStatusOut"]> = {}) {
  const base = syncStatus();
  return syncStatus({
    accounts: [{ id: "acc-1", status: "active", quota_remaining: 98_500, checked_at: minutesAgo(7) }],
    shops: [
      { ...base.shops[0], history_status: "2020-01-01", errors_24h: 0, kinds: [kind({ kind: "orders", fetched: 2465, total: 2465 }), kind({ kind: "expenses" })] },
      {
        ...base.shops[1],
        alias: "Elone",
        history_status: null,
        errors_24h: 3,
        healthy: false,
        kinds: [
          kind({ kind: "orders", status: "error", error: "Uzum 502 Bad Gateway", last_success_at: null, fetched: null }),
          kind({ kind: "products", status: "running", fetched: 40, total: 400 }),
          kind({ kind: "invoices", status: "skipped" }),
          kind({ kind: "returns", status: null, last_success_at: null, fetched: null }),
        ],
      },
    ],
    ...over,
  });
}

async function renderStatus(routes: Routes = {}) {
  const api = mockApi({ [SYNC_ROUTE]: () => json(200, status()), ...routes });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/status"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Maʼlumotlar holati" });
  return api;
}

const rows = (table: HTMLElement) =>
  within(table).getAllByRole("row").slice(1).map((r) => [...r.querySelectorAll("th,td")].map((c) => c.textContent));

describe("Maʼlumotlar holati", () => {
  it("har do'kon — o'z jadvali: tur, holat (ikon + matn), oxirgi muvaffaqiyatli, yozuvlar, xato", async () => {
    await renderStatus();
    const durii = await screen.findByRole("table", { name: "byDurii: Maʼlumotlar holati" });
    expect(rows(durii)).toEqual([
      ["Sotuvlar", "Yangilangan", "3 daqiqa oldin", `${f.number(2465)} / ${f.number(2465)}`, "—"],
      ["Xarajatlar", "Yangilangan", "3 daqiqa oldin", "120", "—"],
    ]);
    const elone = screen.getByRole("table", { name: "Elone: Maʼlumotlar holati" }); // qisqa nom ustun
    expect(rows(elone)).toEqual([
      ["Sotuvlar", "Xato", "hali yoʻq", "—", "Uzum 502 Bad Gateway"],
      ["Mahsulotlar", "Jarayonda", "3 daqiqa oldin", "40 / 400", "—"],
      ["Postavkalar", "Oʻtkazib yuborilgan", "3 daqiqa oldin", "120", "—"],
      ["Qaytarishlar", "Hali yoʻq", "hali yoʻq", "—", "—"],
    ]);
  });

  it("do'kon sarlavhasida tarix, xatolar soni, birinchi sotuv; faol emas belgisi", async () => {
    const base = status();
    await renderStatus({ [SYNC_ROUTE]: () => json(200, { ...base, shops: [{ ...base.shops[0] }, { ...base.shops[1], active: false }] }) });
    await screen.findByRole("heading", { level: 2, name: "byDurii" });
    const head = (name: string) => screen.getByRole("heading", { level: 2, name }).parentElement!;
    expect(head("byDurii").textContent).toContain("Tarix: 2020-01-01");
    expect(head("byDurii").textContent).toContain(`Birinchi sotuv: ${f.date("2025-03-14")}`);
    expect(head("Elone").textContent).toContain("24 soatda xato: 3");
    expect(head("Elone").textContent).toContain("Faol emas");
  });

  it("akkaunt (kalit): holat, kvota, tekshirilgan vaqt", async () => {
    await renderStatus();
    const accounts = (await screen.findByRole("heading", { level: 2, name: "Uzum kalitlari" })).parentElement!;
    expect(accounts.textContent).toContain("Ishlayapti");
    expect(accounts.textContent).toContain(`Qolgan limit: ${f.number(98500)}`);
    expect(accounts.textContent).toContain("Tekshirildi: 7 daqiqa oldin");
  });

  it.each([
    ["invalid", "Kalit yaroqsiz"],
    ["waf_blocked", "Uzum vaqtincha toʻsdi"],
    ["quota_exhausted", "Kunlik limit tugadi"],
    ["disconnected", "Uzilgan"],
  ])("akkaunt holati %s — %s", async (code, text) => {
    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ accounts: [{ id: "a", status: code, quota_remaining: null, checked_at: null }] })) });
    expect((await screen.findByRole("heading", { level: 2, name: "Uzum kalitlari" })).parentElement!.textContent).toContain(text);
  });

  it("umumiy holat: yangi — faqat 'Yangilandi'; xato — sariq banner; eskirgan; uzilish", async () => {
    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ healthy: true })) });
    // Sahifa ichida (topbar SyncIndicator ham shu matnni ko'rsatadi).
    expect(await within(await screen.findByRole("main")).findByText("Yangilandi: 3 daqiqa oldin")).toBeTruthy();
    expect(screen.queryByText("Sinxronda xato")).toBeNull();
    cleanup();

    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ healthy: false })) });
    expect(await within(await screen.findByRole("main")).findByText("Sinxronda xato")).toBeTruthy();
    cleanup();

    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ freshness: { orders: minutesAgo(130) } })) });
    expect(await within(await screen.findByRole("main")).findByText("Yangilanmagan: 2 soat oldin")).toBeTruthy();
    cleanup();

    const outage = { active: true, since: minutesAgo(20), paused_until: null, recovered_from: null, recovered_at: null };
    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ outage })) });
    expect((await screen.findAllByText("Uzumda uzilish")).length).toBeGreaterThan(0); // karkas banneri (+ topbar belgisi) — sahifa takrorlamaydi
    expect(screen.getAllByText(/Shu paytda sotuv yoʻq deb koʻrinsa, ishonmang/)).toHaveLength(1);
    expect((screen.getByRole("button", { name: "Hozir yangilash" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("'Hozir yangilash': so'rov va xabar; cheklangan bo'lsa tushunarli xabar", async () => {
    const api = await renderStatus();
    fireEvent.click(screen.getByRole("button", { name: "Hozir yangilash" }));
    expect(await screen.findByText("Yangilash boshlandi")).toBeTruthy();
    expect(api.count(REFRESH_ROUTE)).toBe(1);
    cleanup();

    await renderStatus({ [REFRESH_ROUTE]: () => problem(429, "sync_refresh_limited") });
    fireEvent.click(screen.getByRole("button", { name: "Hozir yangilash" }));
    expect(await screen.findByText("Yangilash yaqinda boshlangan. Bir daqiqadan soʻng qayta urining.")).toBeTruthy();
  });

  it("do'kon yo'q — bo'sh holat; holat yuklanmasa — xato matni", async () => {
    await renderStatus({ [SYNC_ROUTE]: () => json(200, status({ shops: [], accounts: [] })) });
    expect(await screen.findByText("Doʻkon ulanmagan")).toBeTruthy();
    cleanup();
    await renderStatus({ [SYNC_ROUTE]: () => problem(403, "forbidden") });
    expect((await screen.findAllByRole("alert"))[0].textContent).toContain("ruxsatingiz yoʻq");
  });

  it("noma'lum tur va holat ham o'z nomi bilan ko'rsatiladi (API kengaysa sahifa buzilmasin)", async () => {
    const base = status();
    await renderStatus({
      [SYNC_ROUTE]: () =>
        json(200, { ...base, shops: [{ ...base.shops[0], kinds: [kind({ kind: "analytics", status: "paused" })] }], accounts: [{ id: "a", status: "frozen", quota_remaining: null, checked_at: null }] }),
    });
    const table = await screen.findByRole("table");
    expect(rows(table)[0].slice(0, 2)).toEqual(["analytics", "paused"]);
    expect(screen.getByText("frozen")).toBeTruthy();
  });

  it("ruscha", async () => {
    localStorage.setItem("up.lang", "ru");
    mockApi({ [SYNC_ROUTE]: () => json(200, status()) });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/status"] }), "ru")} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Состояние данных" })).toBeTruthy();
    expect(await screen.findByRole("table", { name: "byDurii: Состояние данных" })).toBeTruthy();
    expect(screen.getAllByText("Ошибка").length).toBeGreaterThan(0);
  });

  it("kirish imkoniyati (axe-core: jiddiy xato 0)", async () => {
    await renderStatus();
    await screen.findByRole("table", { name: /byDurii/ });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  }, 30_000);
});

