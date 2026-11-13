// Xaridlar (M9) sahifasi uchun sof yordamchilar: holat guruhlari, Partiya yo'li → Timeline, taxminiy
// belgilar (F22). Hisob yo'q — birlik tannarx, kurs va kutilgan sana API'dan (tamoyil 4).
import type { Stage } from "../../components/ui";
import type { PurchaseGroup } from "../../app/search";
import type { AllocationBase, ComponentKind, PathMark, PickerRow, SupplyState } from "../../lib/api/types";

/** Ro'yxat guruhlari → API `state` filtri (ADR-061 §1: guruh — holatning o'zi). */
export const GROUP_STATES: Record<PurchaseGroup, SupplyState[]> = {
  in_transit: ["in_transit"],
  in_stock: ["in_stock"],
  at_uzum: ["at_uzum"],
};

/** Tez xarid valyutalari (ADR-061 §2): hisobdan real yechilgan summa. */
export const PAID_CURRENCIES = ["CNY", "USD", "UZS"] as const;
export type PaidCurrency = (typeof PAID_CURRENCIES)[number];

export const COMPONENT_KINDS: ComponentKind[] = ["goods", "cn_delivery", "agent_fee", "cargo", "customs", "transfer_fee", "local_delivery", "packaging", "labeling", "uzum_delivery", "other"];
/** Kargo xarajati turlari (ADR-049; backend `SHIPMENT_KINDS` bilan bir xil): tovar, Xitoy ichki yetkazish va agent komissiyasi xaridniki. */
export const SHIPMENT_KINDS: ComponentKind[] = ["cargo", "customs", "transfer_fee", "local_delivery", "packaging", "labeling", "uzum_delivery", "other"];
export const ALLOCATIONS: AllocationBase[] = ["units", "weight", "volume", "value", "manual", "line_sum"];
/** Yangi yozuvlarda taqsimot (ADR-061 §3): dona yoki qo'lda (tovar summasi — qator summasi ham); vazn / hajm / qiymat — faqat
 * eski yozuvlarni tahrirlashda (o'z asosida qoladi). */
export const NEW_ALLOCATIONS: AllocationBase[] = ["units", "manual"];
export const CURRENCIES = ["CNY", "USD", "UZS", "EUR", "RUB"] as const;
export type CurrencyCode = (typeof CURRENCIES)[number];

/** Taxminiy (F22): kargo kiritilmagan, qabul qilinmagan (buyurtma donasi bilan), vazn/hajm yo'q — dona bo'yicha, kurs bozor kursi (CBU emas, ADR-045). */
export const ESTIMATE_FLAGS = ["cargo_missing", "not_received", "base_fallback", "market_rate"] as const;

export function isEstimated(flags: readonly string[]): boolean {
  return flags.some((f) => (ESTIMATE_FLAGS as readonly string[]).includes(f));
}

/** Ma'lumot uchun belgilar (taxminiy emas): kurs Markaziy bank bo'yicha; qator summalari kiritilmagan (ADR-061 §2). */
export const INFO_FLAGS = ["no_line_sums", "cbu_rate"] as const;

export function isInfoFlag(flag: string): boolean {
  return (INFO_FLAGS as readonly string[]).includes(flag);
}

/** Ko'rsatiladigan belgilar tartib bilan (ma'lumot uchun belgilar — oxirida). */
export function visibleFlags(flags: readonly string[]): string[] {
  const order = [...ESTIMATE_FLAGS, ...INFO_FLAGS];
  return order.filter((f) => flags.includes(f));
}

/** Uch nuqtali Partiya yo'li (ADR-061 §1, 04 §6.2) → `Timeline`. */
export function pathStages(marks: PathMark[], label: (state: SupplyState) => string): Stage[] {
  return marks.map((m) => ({
    label: label(m.state),
    state: m.mark === "done" ? "done" : m.mark === "current" ? "current" : "upcoming",
    date: m.on ?? undefined,
    days: m.mark === "current" ? (m.days ?? undefined) : undefined,
    expected: m.expected ?? undefined,
    delayed: m.delayed,
  }));
}

// --- Tovar tanlash (SKU) ------------------------------------------------------------------------------------------

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Tanlov qatori kaliti: SKU yoki SKU'siz tovar (`value` sifatida ham ishlatiladi). */
export function pickerKey(row: PickerRow): string {
  return row.sku_id ? `sku:${row.sku_id}` : `item:${row.item_id}`;
}

/** Asosiy nom: mahsulot (Uzum kartochkasi), yo'q bo'lsa tovar yoki SKU nomi. */
export function pickerLabel(row: PickerRow): string {
  return row.product_title || row.item_name || row.title || "—";
}

/**
 * SKU ro'yxatidan tanlov variantlari. Hech narsa holat bo'yicha yashirilmaydi: arxivlangan va bloklangan SKU ham
 * chiqadi, holati belgi bo'lib ko'rinadi (Uzum qiymati o'zgartirilmaydi). `taken` — partiyada allaqachon bor tovarlar.
 */
export function pickerOptions(rows: readonly PickerRow[], t: Translate, taken: ReadonlySet<string>) {
  return rows.map((row) => {
    const label = pickerLabel(row);
    const parts: string[] = [];
    if (row.title && row.title !== label) parts.push(row.title);
    if (row.shop) parts.push(row.shop);
    if (!row.sku_id) parts.push(t("purchases.lines.withoutSku"));
    else if (row.stock !== null) parts.push(row.stock > 0 ? t("purchases.lines.stock", { count: row.stock }) : t("purchases.lines.noStock"));
    if (row.status) parts.push(row.status);
    if (row.item_id && taken.has(row.item_id)) parts.push(t("purchases.lines.inPurchase"));
    return {
      value: pickerKey(row),
      label,
      hint: parts.join(" · "),
      keywords: [row.title, row.article, row.item_name, row.shop].filter(Boolean).join(" "),
    };
  });
}
