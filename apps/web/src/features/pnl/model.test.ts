// Foyda va zarar modeli (M5): qatorlar tartibi va zanjir, sharshara qadamlari, kesim qatorlari, SKU tartibi.
import { describe, expect, it } from "vitest";

import { createI18n } from "../../lib/i18n";
import { pnlData, pnlStatement, skuColumns } from "../../test/pnl";
import { rowLabel } from "../home/model";
import { breakdownLines, pnlLines, skuOrder, waterfallSteps } from "./model";

const t = createI18n("uz-Latn").t;
const label = (code: string) => rowLabel(code, t);
const cents = (value: string) => BigInt(value.replace(".", "").replace(/^(-?)0+(?=\d)/, "$1"));

describe("pnlLines", () => {
  const lines = pnlLines(pnlData().rows, label, "Yalpi foyda");
  const byKey = Object.fromEntries(lines.map((l) => [l.key, l]));

  it("M5 tartibi: tannarxsiz to'lov yalpi foydadan oldin, tannarxsiz xarajat sof foydadan oldin", () => {
    expect(lines.map((l) => l.key)).toEqual([
      "revenue",
      "commission",
      "logistics",
      "payout",
      "uncovered_payout",
      "cogs",
      "gross_profit",
      "uzum:advertising",
      "uzum:compensation",
      "own:ijara",
      "tax",
      "uncovered_expenses",
      "net_profit",
    ]);
    expect(byKey.gross_profit).toMatchObject({ op: "=", kind: "subtotal", formula: "grossProfit", source: { type: "none" } });
    expect(byKey["uzum:compensation"]!.op).toBe("+");
  });

  it("zanjir: har oraliq va yakuniy summa yuqoridagi qatorlar yig'indisiga teng (ishora bilan)", () => {
    let running = 0n;
    for (const line of lines) {
      if (line.op === "=") expect(cents(line.amount)).toBe(running);
      else running += cents(line.amount);
      if (line.op === "=") running = cents(line.amount);
    }
  });

  it("ustunlar API'dan; tannarxsiz to'lov — ayiriluvchi, ustunlari ham teskari ishorada", () => {
    expect(byKey.revenue).toMatchObject({ share: "1.000000", previous: "8000000.00", diff: "2000000.00", change: "0.250000" });
    expect(byKey.uncovered_payout).toMatchObject({ amount: "-750000.00", share: "-0.075000", previous: "-400000.00", diff: "-350000.00", change: null });
  });

  it("Uzum va o'z xarajati yo'q — nol qatorlar (tuzilma o'zgarmaydi)", () => {
    const rows = pnlData().rows.filter((r) => !r.code.startsWith("uzum:") && !r.code.startsWith("own:"));
    const keys = pnlLines(rows, label, "Yalpi foyda").map((l) => l.key);
    expect(keys.slice(7, 10)).toEqual(["uzum", "own", "tax"]);
  });

  it("tannarxsiz qism yo'q — yalpi foyda tannarxdan keyin", () => {
    const rows = pnlData().rows.filter((r) => !r.code.startsWith("uncovered"));
    const keys = pnlLines(rows, label, "Yalpi foyda").map((l) => l.key);
    expect(keys.slice(3, 6)).toEqual(["payout", "cogs", "gross_profit"]);
  });
});

describe("waterfallSteps", () => {
  const steps = waterfallSteps(pnlStatement(), (k) => k);

  it("tushumdan sof foydagacha; ayiriluvchi manfiy, oraliq summalar — yakuniy", () => {
    expect(steps.map((s) => [s.key, s.kind, s.amount])).toEqual([
      ["revenue", "add", "10000000.00"],
      ["commission", "subtract", "-2000000.00"],
      ["logistics", "subtract", "-500000.00"],
      ["payout", "total", "7500000.00"],
      ["uncoveredPayout", "subtract", "-750000.00"],
      ["cogs", "subtract", "-3000000.00"],
      ["gross", "total", "3750000.00"],
      ["uzum", "subtract", "-300000.00"],
      ["own", "subtract", "-200000.00"],
      ["tax", "subtract", "-100000.00"],
      ["uncoveredExpenses", "add", "60000.00"],
      ["net", "total", "3210000.00"],
    ]);
  });

  it("zanjir yig'indisi yakuniy qadamlarga teng", () => {
    let level = 0n;
    for (const s of steps) {
      if (s.kind === "total") expect(cents(s.amount)).toBe(level);
      else level += cents(s.amount);
    }
  });

  it("tannarxsiz qism yo'q — qadamlari yo'q; Uzum xarajati manfiy (kompensatsiya ko'p) — qo'shiluvchi", () => {
    const s = pnlStatement({
      uncovered: { lines: 0, revenue: "0.00", payout: "0.00", expenses: "0.00", share: "0.000000" },
      uzum_total: "-50000.00",
    });
    const keys = waterfallSteps(s, (k) => k);
    expect(keys.map((x) => x.key)).not.toContain("uncoveredPayout");
    expect(keys.map((x) => x.key)).not.toContain("uncoveredExpenses");
    expect(keys.find((x) => x.key === "uzum")).toMatchObject({ kind: "add", amount: "50000.00" });
  });
});

describe("breakdownLines", () => {
  it("oylar: jami qatorlar; do'kon/SKU: F9/F10 to'g'ridan-to'g'ri va taqsimlangan (ADR-026)", () => {
    const month = breakdownLines(t, false);
    expect(month.map((l) => l.key)).not.toContain("uzum_direct");
    const shop = breakdownLines(t, true);
    const keys = shop.map((l) => l.key);
    expect(keys.slice(keys.indexOf("uzum"), keys.indexOf("tax"))).toEqual(["uzum", "uzum_direct", "uzum_allocated", "own", "own_direct", "own_allocated"]);
    const s = pnlStatement();
    const value = (key: string) => shop.find((l) => l.key === key)!.value(s);
    expect(value("uzum_direct")).toBe("-250000.00");
    expect(value("own_allocated")).toBe("-200000.00");
    expect(value("own_direct")).toBe("0.00");
    expect(value("margin")).toBe("0.356667");
    expect(shop.find((l) => l.key === "uzum_direct")!.label).toBe("Uzum xarajatlari — toʻgʻridan-toʻgʻri");
  });
});

describe("skuOrder", () => {
  it("sof foyda bo'yicha kamayish; bog'lanmagan va taqsimlanmagan — oxirida", () => {
    expect(skuOrder(skuColumns()).map((c) => c.key)).toEqual(["s-top", "s-loss", "unlinked", null]);
  });
});
