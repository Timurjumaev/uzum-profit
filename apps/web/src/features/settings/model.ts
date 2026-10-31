// Sozlamalar (M16) uchun sof yordamchilar: soliq profili shakli (rejimga mos maydonlar), muddat va qamrov
// kiritishlari. Hisob yo'q — F-formulalar serverda (tamoyil 4); bu yerda faqat kiritish tekshiruvi.
import type { InventorySettingsIn, Settings, TaxBase, TaxProfile, TaxProfileIn, TaxRegime } from "../../lib/api/types";

export const REGIMES: TaxRegime[] = ["turnover", "agent", "vat_profit", "none"];
export const BASES: TaxBase[] = ["revenue", "payout"];
export const PAYOUT_KINDS = ["daily", "weekly", "biweekly", "monthly"] as const;

export type TaxDraft = { valid_from: string; regime: TaxRegime; rate: string | null; base: TaxBase; vat: string | null; profit: string | null };

/** Qatordan forma (stavka "4.000" → "4": ortiqcha nol tashlanadi). */
export function taxDraft(p: TaxProfile | null, today: string): TaxDraft {
  if (!p) return { valid_from: today, regime: "turnover", rate: null, base: "revenue", vat: null, profit: null };
  const pct = (v: string) => (Number(v) === 0 ? null : String(Number(v)));
  return { valid_from: p.valid_from, regime: p.regime, rate: pct(p.rate_pct), base: p.base, vat: pct(p.vat_pct), profit: pct(p.profit_pct) };
}

const inRange = (v: string | null) => v === null || (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 100);

/** Forma to'g'rimi: aylanma solig'ida stavka 0 dan katta, foizlar 0–100, sana bor. */
export function taxValid(d: TaxDraft): boolean {
  if (!d.valid_from) return false;
  if (d.regime === "turnover") return d.rate !== null && Number(d.rate) > 0 && inRange(d.rate);
  if (d.regime === "vat_profit") return inRange(d.vat) && inRange(d.profit);
  return true;
}

/** Serverga: rejimga tegishli bo'lmagan maydonlar nol/standart (server ham shunday normallashtiradi). */
export function taxBody(d: TaxDraft): TaxProfileIn {
  const turnover = d.regime === "turnover";
  const vat = d.regime === "vat_profit";
  return {
    valid_from: d.valid_from,
    regime: d.regime,
    rate_pct: turnover ? (d.rate ?? "0") : "0",
    base: turnover ? d.base : "revenue",
    vat_pct: vat ? (d.vat ?? "0") : "0",
    profit_pct: vat ? (d.profit ?? "0") : "0",
  };
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
