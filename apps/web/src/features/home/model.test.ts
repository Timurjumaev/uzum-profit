// Bosh sahifa modeli (M4): hisob varag'i qatorlari, tuzilma, yo'nalish va "Diqqat talab qiladi" tartibi.
import { describe, expect, it } from "vitest";

import { createI18n } from "../../lib/i18n";
import { dashboardData } from "../../test/api";
import { attentionItems, homeRows, negate, rowLabel } from "./model";

const t = createI18n("uz-Latn").t;
const label = (code: string) => rowLabel(code, t);
const cents = (value: string) => BigInt(value.replace(".", "").replace(/^(-?)0+(?=\d)/, "$1"));

describe("negate", () => {
  it("ishorani almashtiradi, nol ishorasiz qoladi", () => {
    expect(negate("0.129818")).toBe("-0.129818");
    expect(negate("-37284000.00")).toBe("37284000.00");
    expect(negate("0")).toBe("0");
    expect(negate("0.00")).toBe("0.00");
    expect(negate("-0.000000")).toBe("-0.000000");
  });
});

describe("rowLabel", () => {
  it("atamalar lug'ati, Uzum toifalari, o'z toifa nomi", () => {
    expect(label("revenue")).toBe("Tushum");
    expect(label("payout")).toBe("Uzum toʻlovi");
    expect(label("net_profit")).toBe("Sof foyda");
    expect(label("uzum:advertising")).toBe("Reklama");
    expect(label("uzum:yangi_toifa")).toBe("yangi_toifa"); // noma'lum toifa — kodning o'zi
    expect(label("own:Ijara")).toBe("Ijara");
    expect(label("uzum")).toBe("Uzum xarajatlari");
    expect(label("own")).toBe("Oʻz xarajatlarim");
  });
});

describe("homeRows", () => {
  const rows = homeRows(dashboardData().rows, label);
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r]));

  it("tartib: tushum → … → Uzum to'lovi → tannarx → xarajatlar → soliq → sof foyda; yalpi foyda yo'q", () => {
    expect(rows.map((r) => r.key)).toEqual([
      "revenue",
      "commission",
      "logistics",
      "payout",
      "cogs",
      "uzum:advertising",
      "uzum:storage",
      "own", // o'z xarajati yo'q — nol qator, tuzilma o'zgarmaydi
      "tax",
      "net_profit",
    ]);
  });

  it("belgilar: operator, oraliq summa va yakun", () => {
    expect(byKey.revenue.op).toBe("");
    expect(byKey.commission.op).toBe("−");
    expect(byKey.payout).toMatchObject({ op: "=", kind: "subtotal" });
    expect(byKey.net_profit).toMatchObject({ op: "=", kind: "total" });
    expect(byKey.own).toMatchObject({ amount: "0", change: null, source: { type: "none" } });
  });

  it("drill-down manbasi: sotuv, Uzum toifasi, hisoblanadigan qator", () => {
    expect(byKey.revenue.source).toEqual({ type: "sales" });
    expect(byKey.cogs.source).toEqual({ type: "sales" });
    expect(byKey["uzum:storage"].source).toEqual({ type: "uzum", category: "storage" });
    expect(byKey.tax.source).toEqual({ type: "none" });
    expect(byKey.net_profit.source).toEqual({ type: "none" });
  });

  it("mobilda yig'ilganda faqat tushum, Uzum to'lovi va sof foyda ko'rinadi", () => {
    expect(rows.filter((r) => !r.compactHidden).map((r) => r.key)).toEqual(["revenue", "payout", "net_profit"]);
  });

  it("yig'indi: tushum + xarajat qatorlari = sof foyda (to'lov va yakun — oraliq)", () => {
    const parts = rows.filter((r) => r.kind === "row");
    const sum = parts.reduce((acc, r) => acc + cents(r.amount), 0n);
    expect(sum).toBe(cents(byKey.net_profit.amount));
  });

  it("o'zgarish API'dan: xarajat qatorida kattalik bo'yicha, tushumda ishorali", () => {
    expect(byKey.commission.change).toBe("-0.129818"); // API ishorali: xarajat o'sdi
    expect(byKey.commission.direction).toBe("cost");
    expect(byKey.revenue.direction).toBe("income");
  });

  it("tannarxsiz qism: to'lov ayriladi, xarajat qaytariladi, o'zgarishsiz — zanjir yig'indisi to'g'ri", () => {
    const data = dashboardData();
    const extra = [
      { code: "uncovered_payout", amount: "1000000.00", share_of_revenue: null, previous: "0.00", diff: "1000000.00", change: null },
      { code: "uncovered_expenses", amount: "120000.00", share_of_revenue: null, previous: "0.00", diff: "120000.00", change: null },
    ];
    const at = data.rows.findIndex((r) => r.code === "net_profit");
    const withUncovered = homeRows([...data.rows.slice(0, at), ...extra, ...data.rows.slice(at)], label);
    const m = Object.fromEntries(withUncovered.map((r) => [r.key, r]));
    expect(m.uncovered_payout).toMatchObject({ op: "−", amount: "-1000000.00", change: null });
    expect(m.uncovered_expenses).toMatchObject({ op: "+", amount: "120000.00", change: null });
    expect(withUncovered.map((r) => r.key).slice(-3)).toEqual(["uncovered_payout", "uncovered_expenses", "net_profit"]);
  });

  it("kompensatsiya (musbat Uzum qatori) — plyus", () => {
    const rows2 = homeRows(
      [
        { code: "tax", amount: "0.00", share_of_revenue: null, previous: "0.00", diff: "0.00", change: null },
        { code: "uzum:compensation", amount: "50000.00", share_of_revenue: null, previous: "0.00", diff: "50000.00", change: null },
      ],
      label,
    );
    expect(rows2.find((r) => r.key === "uzum:compensation")?.op).toBe("+");
  });
});

describe("attentionItems", () => {
  const base = dashboardData().attention;

  it("ustuvorlik tartibi, nol bo'lganlari tushiriladi", () => {
    const items = attentionItems(
      { ...base, uncosted_lines: 12, uncosted_revenue: "1240000.00", stock_critical: 2, stock_high: 3, loss_skus: 1, recalculated: 4 },
      1,
    );
    expect(items.map((i) => i.kind)).toEqual(["uncosted", "stockCritical", "stockHigh", "lossSkus", "sync", "recalculated"]);
    expect(items[0]).toMatchObject({ tone: "warning", count: 12, amount: "1240000.00", to: "/products" });
    expect(items[1]).toMatchObject({ tone: "negative", to: "/inventory" });
    expect(attentionItems({ ...base, loss_skus: 0, stock_critical: 0, stock_high: 0 }, 0)).toEqual([]);
  });
});
