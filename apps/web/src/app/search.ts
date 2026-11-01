// URL qidiruv parametrlari: tekshiruvchilar (router) va iste'molchilar (komponentlar) bir joyda. MUHIM: TanStack
// Router bola marshrutga ota marshrutning xom qidiruvini ham beradi (`useSearch` tekshirilmagan qiymatni qaytarishi
// mumkin), shuning uchun xavfsizlik uchun muhim qiymat (qaytish manzili, taklif tokeni) ISHLATILGAN joyda ham shu
// funksiyalardan o'tkaziladi.

export type LoginSearch = { redirect?: string };

/** Kirishdan keyin qaytish manzili — faqat o'z saytimiz ichidagi yo'l (ochiq qayta yo'naltirish yo'q). */
export function loginSearch(search: Record<string, unknown>): LoginSearch {
  const target = search.redirect;
  return typeof target === "string" && /^\/(?![/\\])/.test(target) ? { redirect: target } : {};
}

export type InviteSearch = { token?: string };

/** Taklif havolasi tokeni: faqat harf, raqam, `_` va `-`. */
export function inviteSearch(search: Record<string, unknown>): InviteSearch {
  return typeof search.token === "string" && /^[\w-]{8,200}$/.test(search.token) ? { token: search.token } : {};
}

export const ONBOARDING_STEPS = ["org", "key", "shops", "history"] as const;
export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];
export type OnboardingSearch = { step?: OnboardingStep };

export function onboardingSearch(search: Record<string, unknown>): OnboardingSearch {
  return (ONBOARDING_STEPS as readonly unknown[]).includes(search.step) ? { step: search.step as OnboardingStep } : {};
}

export const PNL_VIEWS = ["month", "shop", "sku"] as const;
export type PnlSearch = { view?: (typeof PNL_VIEWS)[number] };

/** P&L kesimi (M5): oylar (standart — URL'da yozilmaydi), do'konlar, SKU. */
export function pnlSearch(search: Record<string, unknown>): PnlSearch {
  return search.view === "shop" || search.view === "sku" ? { view: search.view } : {};
}

export const PRODUCT_SORTS = [
  "revenue",
  "net_profit",
  "units",
  "margin",
  "title",
  "stock",
  "days_of_stock",
  "avg_price",
  "profit_per_unit",
  "roi",
  "return_share",
  "cancel_share",
  "expenses_direct",
  "expenses_allocated",
] as const;
export type ProductSort = (typeof PRODUCT_SORTS)[number];
export const PRODUCT_LABELS = ["loss", "borderline", "profitable", "no_data"] as const;
export type ProductLabel = (typeof PRODUCT_LABELS)[number];
export const PRODUCT_ABC = ["A", "B", "C"] as const;
export type ProductAbc = (typeof PRODUCT_ABC)[number];

/** Standart saralash: tushum kamayish tartibida (URL'da yozilmaydi). */
export const DEFAULT_PRODUCT_SORT = { key: "revenue", desc: true } as const;

export type ProductsSearch = { q?: string; sort?: string; label?: ProductLabel; abc?: ProductAbc };

/** Mahsulotlar jadvali (M6): qidiruv, saralash (`-` — kamayish), holat va ABC filtrlari — havola bilan ulashiladi. */
export function productsSearch(search: Record<string, unknown>): ProductsSearch {
  const out: ProductsSearch = {};
  if (typeof search.q === "string" && search.q.trim() !== "") out.q = search.q.slice(0, 100);
  if (typeof search.sort === "string") {
    const key = search.sort.replace(/^-/, "");
    if ((PRODUCT_SORTS as readonly string[]).includes(key) && search.sort !== `-${DEFAULT_PRODUCT_SORT.key}`) out.sort = search.sort;
  }
  if ((PRODUCT_LABELS as readonly unknown[]).includes(search.label)) out.label = search.label as ProductLabel;
  if ((PRODUCT_ABC as readonly unknown[]).includes(search.abc)) out.abc = search.abc as ProductAbc;
  return out;
}

/** `sort` qiymati → kalit va yo'nalish (`title` — o'sish, qolganlari — kamayish: eng kattasi tepada). */
export function parseSort(sort: string | undefined): { key: ProductSort; desc: boolean } {
  const key = (sort ?? "").replace(/^-/, "");
  if (!(PRODUCT_SORTS as readonly string[]).includes(key)) return { ...DEFAULT_PRODUCT_SORT };
  return { key: key as ProductSort, desc: (sort ?? "").startsWith("-") };
}

export const ORDER_TABS = ["list", "cancel", "returns"] as const;
export type OrderTab = (typeof ORDER_TABS)[number];
export const ORDER_GROUPS = ["completed", "processing", "canceled"] as const;
export type OrderGroup = (typeof ORDER_GROUPS)[number];

export type OrdersSearch = { tab?: Exclude<OrderTab, "list">; group?: OrderGroup };

/** Buyurtmalar (M7): bo'lim (ro'yxat — standart, URL'da yo'q) va ro'yxat holati filtri — havola bilan ulashiladi. */
export function ordersSearch(search: Record<string, unknown>): OrdersSearch {
  const out: OrdersSearch = {};
  if (search.tab === "cancel" || search.tab === "returns") out.tab = search.tab;
  if ((ORDER_GROUPS as readonly unknown[]).includes(search.group)) out.group = search.group as OrderGroup;
  return out;
}

export type ExpensesSearch = { section?: "own" };

/** Xarajatlar (M8): bo'lim (`section`) — Uzum xarajatlari (standart, URL'da yo'q) yoki o'z xarajatlarim. */
export function expensesSearch(search: Record<string, unknown>): ExpensesSearch {
  return search.section === "own" ? { section: "own" } : {};
}

export const PURCHASE_GROUPS = ["active", "draft", "transit", "closed"] as const;
export type PurchaseGroup = (typeof PURCHASE_GROUPS)[number];
export type PurchasesSearch = { group?: PurchaseGroup };

/** Xaridlar (M9): bosqich guruhi (`group`) — standart "hammasi" (URL'da yo'q). */
export function purchasesSearch(search: Record<string, unknown>): PurchasesSearch {
  return (PURCHASE_GROUPS as readonly unknown[]).includes(search.group) ? { group: search.group as PurchaseGroup } : {};
}

export const STOCK_STATUSES = ["critical", "high", "medium", "good", "dead"] as const;
export type StockStatusId = (typeof STOCK_STATUSES)[number];
export type InventorySearch = { status?: StockStatusId; q?: string };

/** Ombor (M10): holat guruhi (`status`, standart "hammasi") va qidiruv (`q`) — havola bilan ulashiladi. */
export function inventorySearch(search: Record<string, unknown>): InventorySearch {
  const out: InventorySearch = {};
  if ((STOCK_STATUSES as readonly unknown[]).includes(search.status)) out.status = search.status as StockStatusId;
  if (typeof search.q === "string" && search.q.trim() !== "") out.q = search.q.slice(0, 100);
  return out;
}
