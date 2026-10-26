// Bosh sahifa modeli (M4): API javobi → ekran qatorlari. Hisoblash yo'q (tamoyil 4) — summa, o'zgarish ulushi va
// sanoqlar API'dan; bu yerda faqat tartib, belgi (ikon/rang uchun yo'nalish) va matn kalitlari.
import type { TFunction } from "i18next";

import type { LedgerRow } from "../../components/ui";
import type { Dashboard, PnlRow } from "../../lib/api/types";
import { term } from "../../lib/i18n/glossary";

/** Qator yo'nalishi: xarajat — kattalashishi yomon (o'zgarish kattalik bo'yicha ko'rsatiladi), qolgani — ishorali. */
export type Direction = "income" | "cost";

export type HomeRow = LedgerRow & {
  /** Drill-down manbasi: sotuv qatorlari, Uzum toifasi xarajatlari, o'z xarajatlari yoki yo'q (faqat formula). */
  source: { type: "sales" | "uzum" | "own"; category?: string } | { type: "none" };
  /** F-raqam va formula kaliti (`home.formula.<formula>`); `null` — formulasiz (tushuntirish matni yo'q). */
  formula: string | null;
  /** O'zgarish ulushi (API: farq / |oldingi|) — yo'nalishga ko'ra ko'rsatiladi; `null` — oldingi davr nol. */
  change: string | null;
  direction: Direction;
  /** Mobilda yig'ilgan ko'rinishda ko'rinadigan qator (tushum, Uzum to'lovi, sof foyda). */
  keep: boolean;
};

/** "12.5" ↔ "-12.5": nol ishorasiz qoladi. */
export function negate(value: string): string {
  if (/^-?0+(\.0*)?$/.test(value)) return value;
  return value.startsWith("-") ? value.slice(1) : `-${value}`;
}

const isNegative = (value: string) => value.startsWith("-") && !/^-0+(\.0*)?$/.test(value);

type Spec = Pick<HomeRow, "op" | "kind" | "source" | "formula" | "direction" | "keep">;

const FIXED: Record<string, Spec> = {
  revenue: { op: "", kind: "row", source: { type: "sales" }, formula: "revenue", direction: "income", keep: true },
  commission: { op: "−", kind: "row", source: { type: "sales" }, formula: "commission", direction: "cost", keep: false },
  logistics: { op: "−", kind: "row", source: { type: "sales" }, formula: "logistics", direction: "cost", keep: false },
  payout: { op: "=", kind: "subtotal", source: { type: "sales" }, formula: "payout", direction: "income", keep: true },
  cogs: { op: "−", kind: "row", source: { type: "sales" }, formula: "cogs", direction: "cost", keep: false },
  tax: { op: "−", kind: "row", source: { type: "none" }, formula: "tax", direction: "cost", keep: false },
  net_profit: { op: "=", kind: "total", source: { type: "none" }, formula: "netProfit", direction: "income", keep: true },
};

/** Qator matni: atamalar lug'ati (04 §8.2) va Uzum toifalari; o'z xarajatida — foydalanuvchi bergan toifa nomi. */
export function rowLabel(code: string, t: TFunction): string {
  if (code.startsWith("uzum:")) return t(`home.expense.${code.slice(5)}`, { defaultValue: code.slice(5) });
  if (code.startsWith("own:")) return code.slice(4);
  switch (code) {
    case "revenue": return t(term("revenue"));
    case "commission": return t(term("commission"));
    case "logistics": return t(term("logistics"));
    case "payout": return t(term("payout"));
    case "cogs": return t(term("cogs"));
    case "tax": return t(term("tax"));
    case "net_profit": return t(term("netProfit"));
    case "uzum": return t(term("uzumExpenses"));
    case "own": return t(term("ownExpenses"));
    default: return t(`home.ledger.${code}`, { defaultValue: code });
  }
}

const COST = { kind: "row", direction: "cost", keep: false } as const;
const NONE = { type: "none" } as const;
const ZERO_UZUM: Spec = { ...COST, op: "−", source: NONE, formula: "uzumExpenses" };
const ZERO_OWN: Spec = { ...COST, op: "−", source: NONE, formula: "ownExpenses" };

/** Xarajat qatori belgisi: manfiy (yoki nol) — "−", musbat (masalan, kompensatsiya) — "+". */
const signOp = (amount: string): "−" | "+" => (isNegative(amount) || Number(amount) === 0 ? "−" : "+");

type Found = { spec: Spec; amount?: string; change?: null };

function specOf(row: PnlRow): Found | null {
  const fixed = FIXED[row.code];
  if (fixed) return { spec: fixed };
  if (row.code.startsWith("uzum:")) {
    return { spec: { ...COST, op: signOp(row.amount), source: { type: "uzum", category: row.code.slice(5) }, formula: "uzumExpenses" } };
  }
  if (row.code.startsWith("own:")) {
    return { spec: { ...COST, op: signOp(row.amount), source: { type: "own", category: row.code.slice(4) }, formula: "ownExpenses" } };
  }
  // Tannarxsiz qism (F15) foydaga kirmagan: zanjir yig'indisi to'g'ri chiqishi uchun to'lov ayriladi, xarajat qaytariladi.
  if (row.code === "uncovered_payout") {
    return { spec: { ...COST, op: "−", source: NONE, formula: "uncovered" }, amount: negate(row.amount), change: null };
  }
  if (row.code === "uncovered_expenses") {
    return { spec: { kind: "row", direction: "income", keep: false, op: "+", source: NONE, formula: "uncovered" }, change: null };
  }
  return null; // yalpi foyda (P&L sahifasida) va noma'lum kodlar
}

function toRow(row: PnlRow, label: string, found: Found): HomeRow {
  const { spec } = found;
  return {
    key: row.code,
    label,
    amount: found.amount ?? row.amount,
    op: spec.op,
    kind: spec.kind,
    source: spec.source,
    formula: spec.formula,
    direction: spec.direction,
    keep: spec.keep,
    compactHidden: !spec.keep,
    change: found.change === null ? null : row.change,
  };
}

/** Hisob varag'i qatorlari (04 §6.1): API tartibi — tushum → komissiya → logistika → = Uzum to'lovi → tannarx → Uzum
 * xarajatlari (toifa bo'yicha) → o'z xarajatlari → soliq → tannarxsiz qism → = sof foyda. Uzum yoki o'z xarajati
 * bo'lmasa shu nomli nol qator qo'shiladi (tuzilma o'zgarmasin). */
export function homeRows(rows: PnlRow[], label: (code: string) => string): HomeRow[] {
  const out: HomeRow[] = [];
  const missing = [
    { code: "uzum", present: rows.some((r) => r.code.startsWith("uzum:")), spec: ZERO_UZUM },
    { code: "own", present: rows.some((r) => r.code.startsWith("own:")), spec: ZERO_OWN },
  ].filter((z) => !z.present);
  for (const row of rows) {
    const found = specOf(row);
    if (!found) continue;
    // Xarajat zonasi tugadi (soliqdan boshlab): yetishmayotgan nol qatorlar shu yerda.
    if (row.code === "tax") {
      for (const z of missing) {
        const zero: PnlRow = { code: z.code, amount: "0", share_of_revenue: null, previous: "0", diff: "0", change: null };
        out.push(toRow(zero, label(z.code), { spec: z.spec }));
      }
    }
    out.push(toRow(row, label(row.code), found));
  }
  return out;
}

export type AttentionKind = "uncosted" | "stockCritical" | "stockHigh" | "lossSkus" | "recalculated" | "sync";
export type AttentionItem = { kind: AttentionKind; tone: "negative" | "warning" | "info"; count: number; to: "/products" | "/inventory" | "/orders" | "/status"; amount?: string };

/** "Diqqat talab qiladi" (M4), ustuvorlik bo'yicha: tannarxsiz sotuvlar → tugayotgan tovar → zarar qilayotgan SKU →
 * sinxron xatosi → tannarxi qayta hisoblangan sotuvlar. Yangi jarimalar, kechikayotgan kargo, Uzum to'lovi — B5. */
export function attentionItems(a: Dashboard["attention"], syncIssues: number): AttentionItem[] {
  const items: AttentionItem[] = [];
  if (a.uncosted_lines > 0) items.push({ kind: "uncosted", tone: "warning", count: a.uncosted_lines, to: "/products", amount: a.uncosted_revenue });
  if (a.stock_critical > 0) items.push({ kind: "stockCritical", tone: "negative", count: a.stock_critical, to: "/inventory" });
  if (a.stock_high > 0) items.push({ kind: "stockHigh", tone: "warning", count: a.stock_high, to: "/inventory" });
  if (a.loss_skus > 0) items.push({ kind: "lossSkus", tone: "negative", count: a.loss_skus, to: "/products" });
  if (syncIssues > 0) items.push({ kind: "sync", tone: "warning", count: syncIssues, to: "/status" });
  if (a.recalculated > 0) items.push({ kind: "recalculated", tone: "info", count: a.recalculated, to: "/orders" });
  return items;
}
