// Sozlamalar (M16) uchun sof yordamchilar: soliq profili shakli (rejimga mos maydonlar), muddat va qamrov
// kiritishlari. Hisob yo'q — F-formulalar serverda (tamoyil 4); bu yerda faqat kiritish tekshiruvi.
import type { InventorySettingsIn, Settings, TaxBase, TaxLine, TaxLineIn, TaxProfile, TaxProfileIn, TaxRate, TaxRegime } from "../../lib/api/types";

export const REGIMES: TaxRegime[] = ["turnover", "agent", "vat_profit", "none"];
export const BASES: TaxBase[] = ["revenue", "payout"];
export const PAYOUT_KINDS = ["daily", "weekly", "biweekly", "monthly"] as const;

export type LineKind = TaxLineIn["kind"];
export type FixedPeriod = NonNullable<TaxLineIn["period"]>;
export const LINE_PERIODS: FixedPeriod[] = ["month", "quarter", "year"];
export const MAX_TAX_LINES = 10;

/** Soliq qatori shakli (ADR-058). `mode` — qat'iy qatorda summa so'mda yoki BHM sonida. */
export type LineDraft = {
  key: string;
  name: string;
  kind: LineKind;
  rate: string | null;
  base: TaxBase;
  mode: "sum" | "bhm";
  amount: string | null;
  bhm: string | null;
  period: FixedPeriod;
};

export type Taxpayer = NonNullable<TaxProfile["taxpayer"]>;
/** F50 (B4.80): soliq to'lovchi turi — yillik tushum chegarasi uchun; "" — ko'rsatilmagan. */
export const TAXPAYERS: Taxpayer[] = ["individual", "llc", "self_employed"];

export type TaxDraft = { valid_from: string; regime: TaxRegime; lines: LineDraft[]; vat: string | null; profit: string | null; taxpayer: Taxpayer | "" };

let lineSeq = 0;
export function newLine(kind: LineKind, over: Partial<LineDraft> = {}): LineDraft {
  lineSeq += 1;
  return { key: `new-${lineSeq}`, name: "", kind, rate: null, base: "revenue", mode: kind === "fixed" ? "bhm" : "sum", amount: null, bhm: null, period: "month", ...over };
}

const pct = (v: string) => (Number(v) === 0 ? null : String(Number(v)));

function lineDraft(l: TaxLine): LineDraft {
  return {
    key: l.id,
    name: l.name,
    kind: l.kind,
    rate: l.kind === "percent" ? pct(l.rate_pct) : null,
    base: l.base,
    mode: l.amount !== null ? "sum" : "bhm",
    amount: l.amount !== null ? String(Number(l.amount)) : null,
    bhm: l.bhm_count !== null ? String(Number(l.bhm_count)) : null,
    period: l.period,
  };
}

/** Qatordan forma (stavka "4.000" → "4": ortiqcha nol tashlanadi). Qatorsiz aylanma profili (eski) — bitta foizli qator. */
export function taxDraft(p: TaxProfile | null, today: string, legacyName = "Aylanmadan soliq"): TaxDraft {
  if (!p) return { valid_from: today, regime: "turnover", lines: [], vat: null, profit: null, taxpayer: "" };
  let lines: LineDraft[] = [];
  if (p.regime === "turnover") {
    if (p.lines.length > 0) lines = p.lines.map(lineDraft);
    else if (Number(p.rate_pct) > 0) lines = [newLine("percent", { name: legacyName, rate: pct(p.rate_pct), base: p.base })];
  }
  return { valid_from: p.valid_from, regime: p.regime, lines, vat: pct(p.vat_pct), profit: pct(p.profit_pct), taxpayer: p.taxpayer ?? "" };
}

const inRange = (v: string | null) => v === null || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 100);
const positive = (v: string | null) => v !== null && Number.isFinite(Number(v)) && Number(v) > 0;

/** Qator to'g'rimi: nom bor; foizli — stavka 0 dan katta va ≤ 100; qat'iy — summa yoki BHM soni 0 dan katta. */
export function lineValid(l: LineDraft): boolean {
  if (l.name.trim() === "") return false;
  if (l.kind === "percent") return positive(l.rate) && Number(l.rate) <= 100;
  return l.mode === "sum" ? positive(l.amount) : positive(l.bhm);
}

/** Qatorlar: kamida bitta, ko'pi bilan 10 ta, hammasi to'g'ri, nomlar takrorlanmaydi (katta-kichik harfsiz). */
export function linesValid(lines: LineDraft[]): boolean {
  if (lines.length === 0 || lines.length > MAX_TAX_LINES || !lines.every(lineValid)) return false;
  return new Set(lines.map((l) => l.name.trim().toLowerCase())).size === lines.length;
}

/** Forma to'g'rimi: aylanmada qatorlar to'g'ri, foizlar 0–100, sana bor. */
export function taxValid(d: TaxDraft): boolean {
  if (!d.valid_from) return false;
  if (d.regime === "turnover") return linesValid(d.lines);
  if (d.regime === "vat_profit") return inRange(d.vat) && inRange(d.profit);
  return true;
}

export function lineBody(l: LineDraft): TaxLineIn {
  const name = l.name.trim();
  if (l.kind === "percent") return { name, kind: "percent", rate_pct: l.rate ?? "0", base: l.base, period: "month" };
  const value = l.mode === "sum" ? { amount: l.amount ?? "0" } : { bhm_count: l.bhm ?? "0" };
  return { name, kind: "fixed", rate_pct: "0", base: "revenue", period: l.period, ...value };
}

/** Serverga: rejimga tegishli bo'lmagan maydonlar nol/standart (server ham shunday normallashtiradi). */
export function taxBody(d: TaxDraft): TaxProfileIn {
  const turnover = d.regime === "turnover";
  const vat = d.regime === "vat_profit";
  return {
    valid_from: d.valid_from,
    regime: d.regime,
    rate_pct: "0",
    base: "revenue",
    vat_pct: vat ? (d.vat ?? "0") : "0",
    profit_pct: vat ? (d.profit ?? "0") : "0",
    lines: turnover ? d.lines.map(lineBody) : [],
    taxpayer: d.taxpayer === "" ? null : d.taxpayer,
  };
}

export type TaxTemplate = "yatt" | "ecommerce" | "empty";
export const TAX_TEMPLATES: TaxTemplate[] = ["yatt", "ecommerce", "empty"];
/** Shablonning soliq to'lovchi turi (F50): YaTT → YaTT, "MChJ aylanmadan" → MChJ; bo'sh shablon turini o'zgartirmaydi. */
export const TEMPLATE_TAXPAYER: Partial<Record<TaxTemplate, Taxpayer>> = { yatt: "individual", ecommerce: "llc" };

/** Tayyor shablon qatorlari (ADR-058). Stavkalar ma'lumotnomadan (`tax_rates`), BHM soni — shablon standarti (tahrirlanadi). */
export function taxTemplate(kind: TaxTemplate, rates: TaxRate[], names: { turnover: string; social: string }): LineDraft[] {
  const rate = (code: string) => {
    const r = rates.find((x) => x.code === code);
    return r ? String(Number(r.rate_pct)) : null;
  };
  if (kind === "yatt") return [newLine("percent", { name: names.turnover, rate: rate("turnover_individual") }), newLine("fixed", { name: names.social, bhm: "1" })];
  if (kind === "ecommerce") return [newLine("percent", { name: names.turnover, rate: rate("turnover_ecommerce") })];
  return [];
}

/** Kuchda turgan profil: `valid_from` ≤ bugun bo'lgan eng yangisi (ro'yxat yangisi birinchi). */
export function activeTax(profiles: TaxProfile[], today: string): TaxProfile | null {
  return profiles.find((p) => p.valid_from <= today) ?? null;
}

export type LeadDraft = Record<string, string | null>;
export type CoverDraft = Record<"A" | "B" | "C", string | null>;

export const leadDraft = (s: Settings["inventory"]): LeadDraft => Object.fromEntries(s.stages.map((st) => [st, s.lead_days ? String(s.lead_days[st] ?? "") || null : null]));
export const coverDraft = (s: Settings["inventory"]): CoverDraft => ({ A: String(s.cover_days.A), B: String(s.cover_days.B), C: String(s.cover_days.C) });

const whole = (v: string | null, max: number) => v !== null && /^\d+$/.test(v) && Number(v) <= max;

/** Muddatlar: hammasi bo'sh (sozlanmagan) yoki hammasi to'ldirilgan; qamrov — uchalasi ham. */
export function inventoryState(lead: LeadDraft, cover: CoverDraft): "ok" | "partial" | "invalid" {
  const values = Object.values(lead);
  const filled = values.filter((v) => v !== null).length;
  if (filled !== 0 && filled !== values.length) return "partial";
  if (filled > 0 && !values.every((v) => whole(v, 365))) return "invalid";
  return (["A", "B", "C"] as const).every((k) => whole(cover[k], 365)) ? "ok" : "invalid";
}

export function inventoryBody(lead: LeadDraft, cover: CoverDraft): InventorySettingsIn {
  const filled = Object.values(lead).every((v) => v !== null) && Object.keys(lead).length > 0;
  return {
    lead_days: filled ? Object.fromEntries(Object.entries(lead).map(([k, v]) => [k, Number(v)])) : null,
    cover_days: { A: Number(cover.A), B: Number(cover.B), C: Number(cover.C) },
  };
}

/** To'lov jadvali tavsifi: oy kunlari (yoki "har ish kuni") va yechish foizi. */
export function termsDays(days: number[] | null): string {
  return days ? days.join(", ") : "";
}

// --- Ogohlantirish chegaralari (ADR-043): foizda kiritiladi ("30"), API'ga ulush ("0.3") — vergul siljishi, float'siz ---

function shift(value: string, places: number): string {
  const negative = value.startsWith("-");
  const [int = "0", frac = ""] = (negative ? value.slice(1) : value).split(".");
  const digits = int + frac;
  const point = int.length + places;
  const padded = point <= 0 ? "0".repeat(1 - point) + digits : digits.padEnd(point, "0");
  const at = Math.max(point, 1);
  const whole = padded.slice(0, at).replace(/^0+(?=\d)/, "");
  const rest = padded.slice(at).replace(/0+$/, "");
  return (negative ? "-" : "") + whole + (rest ? `.${rest}` : "");
}

/** "0.300000" → "30"; `null` → `null`. */
export const shareToPercent = (share: string | null): string | null => (share === null ? null : shift(share, 2));

/** "30" → "0.3"; `null` → `null`. */
export const percentToShare = (percent: string | null): string | null => (percent === null ? null : shift(percent, -2));

/** Chegara 0 dan katta va 100% dan oshmasligi kerak (bo'sh — o'chirilgan). */
export const alertValid = (percent: string | null): boolean => percent === null || (Number(percent) > 0 && Number(percent) <= 100);
