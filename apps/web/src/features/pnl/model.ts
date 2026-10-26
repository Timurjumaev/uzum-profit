// Foyda va zarar modeli (M5): API javobi → ekran qatorlari, sharshara qadamlari va kesim jadvallari. Hisoblash yo'q
// (tamoyil 4) — summalar, ulushlar va farqlar API'dan; bu yerda tartib, belgi va ko'rsatish uchun ishora almashtirish.
import type { Pnl, PnlRow, Statement } from "../../lib/api/types";
import type { WaterfallStep } from "../../components/charts/options";
import { homeRows, negate, type HomeRow } from "../home/model";

/** Hisob varag'i qatori: bosh sahifa qatori + M5 ustunlari (tushumga nisbatan, oldingi davr, farq). */
export type PnlLine = HomeRow & { share: string | null; previous: string; diff: string; estimated?: boolean };

const neg = (v: string | null) => (v === null ? null : negate(v));

/** M5 tartibi: tushum → komissiya → logistika → = Uzum to'lovi → tannarxsiz sotuvlar → tannarx → = yalpi foyda →
 * Uzum xarajatlari (turlari) → o'z xarajatlari (toifalari) → soliq → tannarxsiz qism xarajati → = sof foyda. Tannarxsiz
 * sotuvlar to'lovi yalpi foydadan oldin ayriladi — zanjir har oraliq summada to'g'ri chiqadi (F8 = ma'lum qism). */
export function pnlLines(rows: PnlRow[], label: (code: string) => string, grossLabel: string): PnlLine[] {
  const byCode = new Map(rows.map((r) => [r.code, r]));
  const lines: PnlLine[] = homeRows(rows, label).map((row) => {
    const api = byCode.get(row.key);
    if (!api) return { ...row, share: null, previous: "0", diff: "0" }; // nol qator (Uzum / o'z xarajati yo'q)
    // Tannarxsiz to'lov ayiriluvchi qator sifatida ko'rsatiladi (bosh sahifadagi kabi) — ustunlar ham teskari ishorada.
    if (row.key === "uncovered_payout") return { ...row, share: neg(api.share_of_revenue), previous: negate(api.previous), diff: negate(api.diff) };
    return { ...row, share: api.share_of_revenue, previous: api.previous, diff: api.diff };
  });
  const gross = byCode.get("gross_profit");
  const uncovered = lines.findIndex((l) => l.key === "uncovered_payout");
  const moved = uncovered >= 0 ? lines.splice(uncovered, 1) : [];
  const cogs = lines.findIndex((l) => l.key === "cogs");
  if (cogs < 0) return lines;
  const grossLine: PnlLine[] = gross
    ? [
        {
          key: "gross_profit",
          label: grossLabel,
          amount: gross.amount,
          op: "=",
          kind: "subtotal",
          source: { type: "none" },
          formula: "grossProfit",
          direction: "income",
          keep: true,
          change: gross.change,
          share: gross.share_of_revenue,
          previous: gross.previous,
          diff: gross.diff,
        },
      ]
    : [];
  lines.splice(cogs, 1, ...moved, lines[cogs], ...grossLine);
  return lines;
}

/** Sharshara (04 §5): tushumdan sof foydagacha. Uzum va o'z xarajatlari — bitta qadam (jami API'dan); tannarxsiz
 * qadamlar faqat nol bo'lmasa. Ayiriluvchi qadam manfiy satr bo'lib beriladi (ishora almashtirish — hisob emas). */
export function waterfallSteps(s: Statement, label: (key: string) => string): WaterfallStep[] {
  const step = (key: string, amount: string, kind: WaterfallStep["kind"]): WaterfallStep => ({ key, label: label(key), amount, kind });
  const isZero = (v: string) => Number(v) === 0;
  const out: WaterfallStep[] = [
    step("revenue", s.revenue, "add"),
    step("commission", negate(s.commission), "subtract"),
    step("logistics", negate(s.logistics), "subtract"),
    step("payout", s.payout, "total"),
  ];
  if (!isZero(s.uncovered.payout)) out.push(step("uncoveredPayout", negate(s.uncovered.payout), "subtract"));
  out.push(step("cogs", negate(s.cogs), "subtract"), step("gross", s.gross_profit, "total"));
  // Uzum xarajati jami manfiy bo'lishi mumkin (kompensatsiya ko'p) — u holda qo'shiluvchi.
  out.push(step("uzum", negate(s.uzum_total), Number(s.uzum_total) < 0 ? "add" : "subtract"));
  out.push(step("own", negate(s.own_total), "subtract"), step("tax", negate(s.tax), "subtract"));
  if (!isZero(s.uncovered.expenses)) out.push(step("uncoveredExpenses", s.uncovered.expenses, "add"));
  out.push(step("net", s.net_profit, "total"));
  return out;
}

export type View = "month" | "shop" | "sku";
export const VIEWS: readonly View[] = ["month", "shop", "sku"];

/** Kesim jadvali qatori (oylar / do'konlar ko'rinishi: qator = P&L qatori, ustun = oy yoki do'kon). */
export type BreakdownLine = {
  key: string;
  label: string;
  op: "" | "−" | "=" | "+";
  kind: "row" | "subtotal" | "total" | "part";
  /** Ustun hisobotidan qiymat (satr; ayiriluvchi — manfiy) yoki nisbat. */
  value: (s: Statement) => string | null;
  ratio?: boolean;
};

/** Kesim qatorlari. `split` — do'kon va SKU kesimlarida F9/F10 to'g'ridan-to'g'ri va taqsimlangan qismlari (ADR-026). */
export function breakdownLines(t: (key: string) => string, split: boolean): BreakdownLine[] {
  const minus = (pick: (s: Statement) => string) => (s: Statement) => negate(pick(s));
  const part = (key: string, base: string, pick: (s: Statement) => string): BreakdownLine => ({
    key,
    label: `${t(base)} — ${t(`pnl.views.${key.endsWith("direct") ? "direct" : "allocated"}`)}`,
    op: "−",
    kind: "part",
    value: minus(pick),
  });
  const lines: BreakdownLine[] = [
    { key: "revenue", label: t("terms.revenue"), op: "", kind: "row", value: (s) => s.revenue },
    { key: "commission", label: t("terms.commission"), op: "−", kind: "row", value: minus((s) => s.commission) },
    { key: "logistics", label: t("terms.logistics"), op: "−", kind: "row", value: minus((s) => s.logistics) },
    { key: "payout", label: t("terms.payout"), op: "=", kind: "subtotal", value: (s) => s.payout },
    { key: "uncovered_payout", label: t("pnl.uncoveredPayout"), op: "−", kind: "row", value: minus((s) => s.uncovered.payout) },
    { key: "cogs", label: t("terms.cogs"), op: "−", kind: "row", value: minus((s) => s.cogs) },
    { key: "gross_profit", label: t("terms.grossProfit"), op: "=", kind: "subtotal", value: (s) => s.gross_profit },
    { key: "uzum", label: t("terms.uzumExpenses"), op: "−", kind: "row", value: minus((s) => s.uzum_total) },
  ];
  if (split) {
    lines.push(part("uzum_direct", "terms.uzumExpenses", (s) => s.uzum_direct), part("uzum_allocated", "terms.uzumExpenses", (s) => s.uzum_allocated_total));
  }
  lines.push({ key: "own", label: t("terms.ownExpenses"), op: "−", kind: "row", value: minus((s) => s.own_total) });
  if (split) {
    lines.push(part("own_direct", "terms.ownExpenses", (s) => s.own_direct), part("own_allocated", "terms.ownExpenses", (s) => s.own_allocated_total));
  }
  lines.push(
    { key: "tax", label: t("terms.tax"), op: "−", kind: "row", value: minus((s) => s.tax) },
    { key: "uncovered_expenses", label: t("pnl.uncoveredExpenses"), op: "+", kind: "row", value: (s) => s.uncovered.expenses },
    { key: "net_profit", label: t("terms.netProfit"), op: "=", kind: "total", value: (s) => s.net_profit },
    { key: "margin", label: t("terms.margin"), op: "", kind: "row", value: (s) => s.margin, ratio: true },
  );
  return lines;
}

/** Ustunlar tartibi: oylar va do'konlar — API tartibida; taqsimlanmagan (`null`) — oxirida (API shunday beradi). */
export type Column = Pnl["columns"][number];

/** SKU ko'rinishi: sof foyda bo'yicha kamayish (teng bo'lsa — nom), bog'lanmagan va taqsimlanmagan — oxirida. */
export function skuOrder(columns: Column[]): Column[] {
  const rank = (c: Column) => (c.key === null ? 2 : c.key === "unlinked" ? 1 : 0);
  return [...columns].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      Number(b.statement.net_profit) - Number(a.statement.net_profit) ||
      (a.title ?? "").localeCompare(b.title ?? ""),
  );
}
