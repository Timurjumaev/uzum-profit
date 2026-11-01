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
