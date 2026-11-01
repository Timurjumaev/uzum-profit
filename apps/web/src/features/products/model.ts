// Mahsulotlar modeli (M6, B4.3): ustunlar, saralash kalitlari, holat belgisi va brauzerda saqlanadigan ko'rinishlar.
// Hisoblash yo'q (tamoyil 4) — raqamlar API'dan; bu yerda faqat tanlov, tartib va matn kalitlari.
import type { ProductAbc, ProductLabel, ProductSort } from "../../app/search";
import type { Tone } from "../../components/ui";

export const COLUMN_IDS = [
  "product",
  "shop",
  "units",
  "revenue",
  "avg_price",
  "commission",
  "logistics",
  "cogs",
  "ads",
  "profit",
  "net",
  "margin",
  "roi",
  "returns",
  "cancel",
  "direct",
  "allocated",
  "stock",
  "days",
  "abc",
  "label",
] as const;
export type ColumnId = (typeof COLUMN_IDS)[number];

/** Birinchi ustun (mahsulot) doim ko'rinadi; qolganlari tanlanadi. */
export const REQUIRED_COLUMNS: readonly ColumnId[] = ["product"];

export const DEFAULT_COLUMNS: readonly ColumnId[] = [
  "product",
  "shop",
  "units",
  "revenue",
  "avg_price",
  "cogs",
  "profit",
  "margin",
  "roi",
  "returns",
  "stock",
  "days",
  "label",
];

/** Ustun → API saralash kaliti (bo'lmasa saralanmaydi). */
export const SORT_KEY: Partial<Record<ColumnId, ProductSort>> = {
  product: "title",
  units: "units",
  revenue: "revenue",
  avg_price: "avg_price",
  profit: "profit_per_unit",
  net: "net_profit",
  margin: "margin",
  roi: "roi",
  returns: "return_share",
  cancel: "cancel_share",
  direct: "expenses_direct",
  allocated: "expenses_allocated",
  stock: "stock",
  days: "days_of_stock",
};

/** Saralash kalitiga mos ustun (ustun ko'rinmasa ham saralash saqlanadi). */
export const COLUMN_OF_SORT: Partial<Record<ProductSort, ColumnId>> = Object.fromEntries(
  Object.entries(SORT_KEY).map(([column, sort]) => [sort, column]),
);

/** Ustun sarlavhasiga biriktirilgan formula (`home.formula.<kalit>`): F-raqam bilan "?" ko'rsatiladi. */
export const COLUMN_FORMULA: Partial<Record<ColumnId, string>> = {
  revenue: "revenue",
  commission: "commission",
  logistics: "logistics",
  cogs: "cogs",
  ads: "drr",
  net: "netProfit",
  margin: "margin",
  roi: "roi",
  returns: "returns",
  cancel: "cancel",
  profit: "profitPerUnit",
  direct: "direct",
  allocated: "allocated",
  days: "stockDays",
};

export const LABEL_TONE: Record<ProductLabel, Tone> = {
  loss: "negative",
  borderline: "warning",
  profitable: "positive",
  no_data: "neutral",
};

export const LABEL_SORT_ORDER: readonly ProductLabel[] = ["loss", "borderline", "profitable", "no_data"];

/** Saralash: shu ustun bosilganda keyingi holat (kalit bir xil bo'lsa yo'nalish almashadi; nom — o'sish, qolgani — kamayish). */
export function nextSort(current: { key: ProductSort; desc: boolean }, key: ProductSort): { key: ProductSort; desc: boolean } {
  if (current.key === key) return { key, desc: !current.desc };
  return { key, desc: key !== "title" };
}

export function sortParam(sort: { key: ProductSort; desc: boolean }): string {
  return `${sort.desc ? "-" : ""}${sort.key}`;
}

// --- Brauzerda saqlash (har foydalanuvchining qulayligi; maxfiy oyna yoki yopiq saqlashda jim o'tkaziladi) ----------

export type SavedView = {
  name: string;
  columns: ColumnId[];
  q?: string;
  sort?: string;
  label?: ProductLabel;
  abc?: ProductAbc;
};

const COLUMNS_KEY = (orgId: string) => `up.products.columns.${orgId}`;
const VIEWS_KEY = (orgId: string) => `up.products.views.${orgId}`;

function read(key: string): unknown {
  try {
    const raw = globalThis.localStorage?.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  try {
    globalThis.localStorage?.setItem(key, JSON.stringify(value));
  } catch {
    // saqlanmasa — faqat shu sessiyada
  }
}

/** Ustunlar tanlovi: noma'lum ustun tashlanadi, majburiy ustun doim bor, tartib — `COLUMN_IDS` bo'yicha. */
export function normalizeColumns(value: unknown): ColumnId[] | null {
  if (!Array.isArray(value)) return null;
  const chosen = new Set(value.filter((id): id is ColumnId => (COLUMN_IDS as readonly unknown[]).includes(id)));
  REQUIRED_COLUMNS.forEach((id) => chosen.add(id));
  return COLUMN_IDS.filter((id) => chosen.has(id));
}

/** Saqlangan ustunlar tanlovi; `null` — foydalanuvchi hali tanlamagan (standart ustunlar). */
export function loadColumns(orgId: string): ColumnId[] | null {
  return normalizeColumns(read(COLUMNS_KEY(orgId)));
}

export function saveColumns(orgId: string, columns: ColumnId[]): void {
  write(COLUMNS_KEY(orgId), columns);
}

export function loadViews(orgId: string): SavedView[] {
  const raw = read(VIEWS_KEY(orgId));
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((v): SavedView[] => {
    const columns = normalizeColumns(v?.columns);
    return typeof v?.name === "string" && v.name.trim() !== "" && columns ? [{ ...v, name: v.name, columns }] : [];
  });
}

export function saveViews(orgId: string, views: SavedView[]): void {
  write(VIEWS_KEY(orgId), views);
}

/** Ko'rinishni nom bo'yicha qo'shadi yoki almashtiradi. */
export function upsertView(views: SavedView[], view: SavedView): SavedView[] {
  return [...views.filter((v) => v.name !== view.name), view].sort((a, b) => a.name.localeCompare(b.name));
}
