// Ombor (M10) sahifasi uchun sof yordamchilar: holat tonlari, joylar, buyurtma sanasi ko'rinishi. Hisob yo'q — holat
// (F26), zaxira kunlari (F24), buyurtma sanasi va tavsiya (F27) API'dan (tamoyil 4).
import type { Tone } from "../../components/ui";
import type { StockLocations, StockRow } from "../../lib/api/types";
import type { StockStatusId } from "../../app/search";

export const STATUS_TONE: Record<StockStatusId, Tone> = { critical: "negative", high: "warning", medium: "info", good: "positive", dead: "neutral" };

/** Uzumdan tashqari va yordamchi joylar (FBO/FBS — "Uzumda" ustunida), ko'rsatish tartibida. */
export const EXTRA_PLACES = ["china", "road", "own", "inbound", "defected", "pending"] as const;
export type ExtraPlace = (typeof EXTRA_PLACES)[number];

/** Nolmas joylar tartib bilan (hammasi nol — bo'sh). */
export function extraPlaces(loc: StockLocations): Array<{ place: ExtraPlace; qty: number }> {
  return EXTRA_PLACES.flatMap((place) => (loc[place] > 0 ? [{ place, qty: loc[place] }] : []));
}

/** Buyurtma sanasi (F27): `now` — kechikkan, `date` — sana bor, `none` — tezlik 0 yoki muddat noma'lum. */
export function orderByKind(row: StockRow): "now" | "date" | "none" {
  if (!row.order_by) return "none";
  return row.order_by.overdue ? "now" : "date";
}

/** "Xarid yaratish" tugmasi: tavsiya miqdor > 0 va tovar bor (tovarsiz SKU'ga qator qo'shib bo'lmaydi). */
export function canReorder(row: StockRow): boolean {
  return row.item_id !== null && (row.reorder?.qty ?? 0) > 0;
}

export function reorderTitle(row: StockRow, prefix: string): string {
  return `${prefix}: ${row.product_title ?? row.title ?? ""}`.trim().slice(0, 200);
}

/** Tanlangan qatorlar bo'yicha jami byudjet: valyutalar bo'yicha alohida (CNY va so'm aralashtirilmaydi). Summalar API'dan
 * (F27 byudjet = miqdor × oxirgi narx) — bu yerda faqat qo'shiladi; butun tiyinlarda (suzuvchi nuqtasiz). Byudjet yo'q
 * (omborchi yoki narx noma'lum) qatorlar `missing` da sanaladi. */
export function budgetTotals(rows: ReadonlyArray<StockRow>): { totals: Array<{ currency: string; amount: string }>; missing: number } {
  const cents = new Map<string, bigint>();
  let missing = 0;
  for (const row of rows) {
    const budget = row.reorder?.budget;
    if (!budget || budget.length === 0) {
      missing += 1;
      continue;
    }
    for (const b of budget) {
      const [whole = "0", frac = ""] = b.amount.split(".");
      const value = BigInt(whole) * 100n + BigInt(`${frac}00`.slice(0, 2)) * (whole.startsWith("-") ? -1n : 1n);
      cents.set(b.currency, (cents.get(b.currency) ?? 0n) + value);
    }
  }
  const totals = [...cents].map(([currency, c]) => ({ currency, amount: `${c / 100n}.${String(c % 100n).padStart(2, "0")}` }));
  return { totals, missing };
}
