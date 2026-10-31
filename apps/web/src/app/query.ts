// Server holati (03 §9): TanStack Query, staleTime 60 s. 4xx qayta so'ralmaydi (ruxsat yoki kiritish masalasi),
// tarmoq/5xx/429 — 2 marta. Sessiya tugasa (401) — kirish sahifasiga (`onUnauthorized`).
import { infiniteQueryOptions, MutationCache, QueryCache, QueryClient, queryOptions } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "../lib/api/client";
import type { ComponentIn, ComponentPatch, ItemLinkIn, LineIn, LinePatch, OwnExpenseIn, OwnExpensePatch, PurchaseIn, PurchasePatch, PurchaseStage, StockMoveIn, TaxProfileIn, TaxProfilePatch, PayoutScheduleIn, InventorySettingsIn, WaiverIn, WaiverPatch } from "../lib/api/types";

export const STALE_MS = 60_000;
export const MAX_RETRIES = 2;

export function shouldRetry(failures: number, error: unknown): boolean {
  if (failures >= MAX_RETRIES) return false;
  return error instanceof ApiError ? error.retryable : true;
}

export function makeQueryClient(onUnauthorized: () => void = () => {}): QueryClient {
  const unauthorized = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: unauthorized }),
    mutationCache: new MutationCache({ onError: unauthorized }),
    defaultOptions: {
      queries: { staleTime: STALE_MS, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
}

/** Joriy foydalanuvchi va tashkilotlari; 401 — kirmagan. */
export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
  retry: (failures, error) => !(error instanceof ApiError && error.status === 401) && shouldRetry(failures, error),
});

/** Tanlangan tashkilot — hozircha birinchisi (tashkilotni almashtirish — M1, B3.7). */
export function currentOrg(me: { orgs: Array<{ id: string; name: string; role: string }> }) {
  return me.orgs[0] ?? null;
}

/** Tashkilot do'konlari (topbar filtri, M2 nomi va rangi bilan). */
export const shopsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "shops"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/shops", { params: { path: { org_id: orgId } } })),
  });

export const SYNC_POLL_MS = 60_000;

/** Sinxron holati (M3): "Yangilandi: ..." ko'rsatkichi va uzilish banneri; har daqiqa yangilanadi. */
export const syncQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "sync"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/sync", { params: { path: { org_id: orgId } } })),
    refetchInterval: SYNC_POLL_MS,
  });

/** "Hozir yangilash" (M3): ustuvor navbat, tashkilot bo'yicha daqiqada bir marta. */
export const refreshSync = (orgId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/sync/refresh", { params: { path: { org_id: orgId } } }));

export const logout = () => unwrap(api.POST("/api/v1/auth/logout"));

// --- Kirish, tashkilot, ulanish (B3.7) ----------------------------------------------------------------------------

/** Kodni Telegram'ga yuborish (M1). `phone` — `+998XXXXXXXXX`. */
export const requestOtp = (phone: string) => unwrap(api.POST("/api/v1/auth/otp", { body: { phone } }));

/** Kod bilan kirish: sessiya cookie'si o'rnatiladi, foydalanuvchi va tashkilotlari qaytadi. */
export const loginWithCode = (phone: string, code: string) => unwrap(api.POST("/api/v1/auth/login", { body: { phone, code } }));

export const updateProfile = (body: { name?: string | null; language?: "uz-Latn" | "uz-Cyrl" | "ru" | null }) =>
  unwrap(api.PATCH("/api/v1/auth/me", { body }));

export const acceptInvite = (token: string) => unwrap(api.POST("/api/v1/invites/accept", { body: { token } }));

export const createOrg = (body: { name: string; inn?: string | null }) => unwrap(api.POST("/api/v1/orgs", { body }));

/** Uzum kaliti: tekshiriladi va shifrlanadi; javobda kalit yo'q (faqat oxirgi 4 belgi). */
export const connectAccount = (orgId: string, token: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/accounts", { params: { path: { org_id: orgId } }, body: { token } }));

export const updateShop = (orgId: string, shopId: string, body: { active?: boolean; alias?: string | null; color?: string | null }) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/shops/{shop_id}", { params: { path: { org_id: orgId, shop_id: shopId } }, body }));

// --- Hisobotlar (B4): davr + do'konlar filtri bilan -----------------------------------------------------------------

/** Hisobot so'rovi parametrlari: `app/filters` dan (bo'sh `shops` — hamma do'kon). */
export type ReportParams = { shops: string[]; start: string; end: string };

const reportQuery = (p: ReportParams) => ({ start: p.start, end: p.end, shop: p.shops.length > 0 ? p.shops : undefined });

/** Bosh sahifa (M4): hisob varag'i, davr chizig'i, kunlik grafik, TOP/zarar SKU, ko'rsatkichlar, "Diqqat talab qiladi". */
export const dashboardQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "dashboard", p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/dashboard", { params: { path: { org_id: orgId }, query: reportQuery(p) } })),
  });

/** Foyda va zarar (M5): hisob varag'i (oldingi davr bilan), kesim ustunlari (`view`), F16, F40. */
export const pnlQuery = (orgId: string, p: ReportParams, view: "month" | "shop" | "sku") =>
  queryOptions({
    queryKey: ["orgs", orgId, "pnl", view, p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/pnl", { params: { path: { org_id: orgId }, query: { ...reportQuery(p), view } } })),
  });

// --- Uzum bonuslari (ADR-031) -------------------------------------------------------------------------------------

/** Bonus davrlari (faol va rad etilgan) va tanlash mumkin bo'lgan bepul xarajat turlari. */
export const feeWaiversQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "fee-waivers"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/fee-waivers", { params: { path: { org_id: orgId } } })),
  });

export const createWaiver = (orgId: string, body: WaiverIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/fee-waivers", { params: { path: { org_id: orgId } }, body }));

export const updateWaiver = (orgId: string, waiverId: string, body: WaiverPatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/fee-waivers/{waiver_id}", { params: { path: { org_id: orgId, waiver_id: waiverId } }, body }));

export const deleteWaiver = (orgId: string, waiverId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/fee-waivers/{waiver_id}", { params: { path: { org_id: orgId, waiver_id: waiverId } } }));

/** Drill-down: Yakunlangan sotuv qatorlari (P&L qatorlari yig'indisi shulardan), kursor bilan sahifalanadi. */
export const salesPage = (orgId: string, p: ReportParams, cursor: string | null) =>
  unwrap(
    api.GET("/api/v1/orgs/{org_id}/sales", {
      params: { path: { org_id: orgId }, query: { ...reportQuery(p), group: "completed", limit: 50, cursor } },
    }),
  );

/** Drill-down: bitta Uzum toifasi xarajatlari va o'z xarajatlari (`own_items` — hamma toifa, mijozda saralanadi). */
export const expensesPage = (orgId: string, p: ReportParams, category: string | null, cursor: string | null) =>
  unwrap(
    api.GET("/api/v1/orgs/{org_id}/expenses", {
      params: { path: { org_id: orgId }, query: { ...reportQuery(p), category, limit: 50, cursor } },
    }),
  );

// --- Mahsulotlar (M6, B4.3) ---------------------------------------------------------------------------------------

export const SKU_PAGE = 200;

export type SkuListParams = { q?: string; sort?: string; label?: string; abc?: string };

/** SKU jadvali: kursor bilan sahifalanadi (`next_cursor`); `placeholderData` bilan filtr o'zgarganda jadval yo'qolmaydi. */
export const skusQuery = (orgId: string, p: ReportParams, l: SkuListParams) =>
  infiniteQueryOptions({
    queryKey: ["orgs", orgId, "skus", p, l],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/skus", {
          params: {
            path: { org_id: orgId },
            query: {
              ...reportQuery(p),
              q: l.q || undefined,
              sort: l.sort,
              label: l.label as "loss" | undefined,
              abc: l.abc as "A" | undefined,
              limit: SKU_PAGE,
              cursor: pageParam,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
  });

/** SKU sahifasi: shu davr hisobi, kunlik tarix, lotlar, qaytish sabablari, kalkulyator boshlang'ich qiymatlari. */
export const skuQuery = (orgId: string, skuId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "sku", skuId, p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/skus/{sku_id}", { params: { path: { org_id: orgId, sku_id: skuId }, query: reportQuery(p) } })),
  });

export type UnitCalcInput = {
  price: string;
  unit_cost: string;
  logistics: string;
  packaging: string;
  commission_pct: string;
  tax_pct: string;
  ads_pct: string;
  target_margin_pct: string | null;
};

/** Unit kalkulyator (F35, F36): hisob serverda (tamoyil 4); kiritish o'zgargan sayin qayta so'raladi. */
export const unitCalcQuery = (orgId: string, input: UnitCalcInput) =>
  queryOptions({
    queryKey: ["orgs", orgId, "unit-calc", input],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/unit-calc", {
          params: { path: { org_id: orgId }, query: { ...input, target_margin_pct: input.target_margin_pct ?? undefined } },
        }),
      ),
  });

/** Bog'lash uchun tovarlar (nom bo'yicha qidiruv). */
export const itemsQuery = (orgId: string, q: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "items", q],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/items", { params: { path: { org_id: orgId }, query: { q: q || undefined } } })),
  });

/** SKU ↔ tovar: mavjud tovarga, yangi tovar sifatida yoki ajratish (`mode: none`). */
export const linkItem = (orgId: string, skuId: string, body: ItemLinkIn) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/skus/{sku_id}/item", { params: { path: { org_id: orgId, sku_id: skuId } }, body }));

// --- Buyurtmalar (M7, B4.4) ---------------------------------------------------------------------------------------

export const ORDERS_PAGE = 50;

/** Sotuv qatorlari ro'yxati (holat filtri bilan), kursor bilan sahifalanadi; `summary` — davr bo'yicha F17, F18. */
export const ordersQuery = (orgId: string, p: ReportParams, group: string | undefined) =>
  infiniteQueryOptions({
    queryKey: ["orgs", orgId, "orders", p, group ?? null],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/sales", {
          params: {
            path: { org_id: orgId },
            query: { ...reportQuery(p), group: group as "completed" | undefined, limit: ORDERS_PAGE, cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
  });

/** Bekor va qaytish tahlili: ulushlar (F17, F18), kunlik trend, sabablar, SKU bo'yicha, qaytim saqlash xarajati. */
export const ordersAnalysisQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "orders-analysis", p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/orders/analysis", { params: { path: { org_id: orgId }, query: reportQuery(p) } })),
  });

// --- Xarajatlar (M8, B4.5) ----------------------------------------------------------------------------------------

/** Xarajatlar sahifasi: Uzum toifalari (F9), oylar, jarimalar, o'z xarajatlarim (F10) — bitta so'rov. */
export const expensesQuery = (orgId: string, p: ReportParams) =>
  queryOptions({ queryKey: ["orgs", orgId, "expenses", "summary", p], queryFn: () => expensesPage(orgId, p, null, null) });

/** O'z xarajat toifalari: mavjudlari va tavsiya etilgan boshlang'ichlar. */
export const ownCategoriesQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "expenses", "categories"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/own-expense-categories", { params: { path: { org_id: orgId } } })),
  });

export const createOwnExpense = (orgId: string, body: OwnExpenseIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/own-expenses", { params: { path: { org_id: orgId } }, body }));

export const updateOwnExpense = (orgId: string, id: string, body: OwnExpensePatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/own-expenses/{expense_id}", { params: { path: { org_id: orgId, expense_id: id } }, body }));

export const deleteOwnExpense = (orgId: string, id: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/own-expenses/{expense_id}", { params: { path: { org_id: orgId, expense_id: id } } }));

// --- Xaridlar (M9, B4.6) ------------------------------------------------------------------------------------------

/** Xaridlar ro'yxati (Partiya yo'li va jonli tannarx bilan); `stages` — joriy bosqich filtri (bo'sh — hammasi). */
export const purchasesQuery = (orgId: string, stages: PurchaseStage[]) =>
  queryOptions({
    queryKey: ["orgs", orgId, "purchases", "list", stages],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/purchases", {
          params: { path: { org_id: orgId }, query: { stage: stages.length > 0 ? stages : undefined } },
        }),
      ),
  });

/** Xarid sahifasi: qatorlar, komponentlar (kurs bilan), jonli birlik tannarx (F20), Partiya yo'li. */
export const purchaseQuery = (orgId: string, purchaseId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "purchases", "one", purchaseId],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/purchases/{purchase_id}", { params: { path: { org_id: orgId, purchase_id: purchaseId } } })),
  });

export const suppliersQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "suppliers"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/suppliers", { params: { path: { org_id: orgId } } })),
  });

export const carriersQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "carriers"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/carriers", { params: { path: { org_id: orgId } } })),
  });

export const createSupplier = (orgId: string, name: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/suppliers", { params: { path: { org_id: orgId } }, body: { name } }));

export const createCarrier = (orgId: string, name: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/carriers", { params: { path: { org_id: orgId } }, body: { name } }));

const purchasePath = (orgId: string, purchaseId: string) => ({ path: { org_id: orgId, purchase_id: purchaseId } });

export const createPurchase = (orgId: string, body: PurchaseIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases", { params: { path: { org_id: orgId } }, body }));

export const updatePurchase = (orgId: string, purchaseId: string, body: PurchasePatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/purchases/{purchase_id}", { params: purchasePath(orgId, purchaseId), body }));

export const deletePurchase = (orgId: string, purchaseId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/purchases/{purchase_id}", { params: purchasePath(orgId, purchaseId) }));

/** "Qayta buyurtma": qatorlar yangi qoralamaga (sanalar, qabul va komponentlarsiz). */
export const copyPurchase = (orgId: string, purchaseId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/copy", { params: purchasePath(orgId, purchaseId) }));

export const createLine = (orgId: string, purchaseId: string, body: LineIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/lines", { params: purchasePath(orgId, purchaseId), body }));

export const updateLine = (orgId: string, purchaseId: string, lineId: string, body: LinePatch) =>
  unwrap(
    api.PATCH("/api/v1/orgs/{org_id}/purchases/{purchase_id}/lines/{line_id}", {
      params: { path: { org_id: orgId, purchase_id: purchaseId, line_id: lineId } },
      body,
    }),
  );

export const deleteLine = (orgId: string, purchaseId: string, lineId: string) =>
  unwrap(
    api.DELETE("/api/v1/orgs/{org_id}/purchases/{purchase_id}/lines/{line_id}", {
      params: { path: { org_id: orgId, purchase_id: purchaseId, line_id: lineId } },
    }),
  );

export const createComponent = (orgId: string, purchaseId: string, body: ComponentIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/components", { params: purchasePath(orgId, purchaseId), body }));

export const updateComponent = (orgId: string, purchaseId: string, componentId: string, body: ComponentPatch) =>
  unwrap(
    api.PATCH("/api/v1/orgs/{org_id}/purchases/{purchase_id}/components/{component_id}", {
      params: { path: { org_id: orgId, purchase_id: purchaseId, component_id: componentId } },
      body,
    }),
  );

export const deleteComponent = (orgId: string, purchaseId: string, componentId: string) =>
  unwrap(
    api.DELETE("/api/v1/orgs/{org_id}/purchases/{purchase_id}/components/{component_id}", {
      params: { path: { org_id: orgId, purchase_id: purchaseId, component_id: componentId } },
    }),
  );

// --- Ombor (M10, B4.7) --------------------------------------------------------------------------------------------

export const INVENTORY_PAGE = 100;

/** Qoldiq jadvali: holat (server filtri), qidiruv, do'konlar; kursor bilan sahifalanadi. `totals` — butun tanlov bo'yicha. */
export const inventoryQuery = (orgId: string, shops: string[], l: { status?: string; q?: string }) =>
  infiniteQueryOptions({
    queryKey: ["orgs", orgId, "inventory", shops, l.status ?? null, l.q ?? null],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/inventory", {
          params: {
            path: { org_id: orgId },
            query: { shop: shops.length > 0 ? shops : undefined, status: l.status as "critical" | undefined, q: l.q || undefined, limit: INVENTORY_PAGE, cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor,
  });

/** Tovarning hisobdan chiqarish va tuzatish yozuvlari (yangisi birinchi). */
export const stockMovesQuery = (orgId: string, itemId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "stock-moves", itemId],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/items/{item_id}/stock-moves", { params: { path: { org_id: orgId, item_id: itemId } } })),
  });

export const createStockMove = (orgId: string, body: StockMoveIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/stock-moves", { params: { path: { org_id: orgId } }, body }));

export const deleteStockMove = (orgId: string, moveId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/stock-moves/{move_id}", { params: { path: { org_id: orgId, move_id: moveId } } }));

// --- Sozlamalar (M16, B4.8) ---------------------------------------------------------------------------------------

export const settingsKey = (orgId: string) => ["orgs", orgId, "settings"] as const;

/** Tannarx usuli, soliq profillari, to'lov jadvallari, standart muddatlar va qamrov (yozuvlar ham shu shaklni qaytaradi). */
export const settingsQuery = (orgId: string) =>
  queryOptions({
    queryKey: settingsKey(orgId),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/settings", { params: { path: { org_id: orgId } } })),
  });

const orgPath = (orgId: string) => ({ path: { org_id: orgId } });

export const setCostMethod = (orgId: string, cost_method: "fifo" | "average") =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/settings/cost-method", { params: orgPath(orgId), body: { cost_method } }));

/** Legacy `uzum.db` (B4.9): fayl xom bayt sifatida; `dryRun` — faqat solishtirma hisobot, hech narsa yozilmaydi. */
export const importLegacy = (orgId: string, file: Blob, dryRun: boolean) =>
  unwrap(
    api.POST("/api/v1/orgs/{org_id}/imports/legacy", {
      params: { path: { org_id: orgId }, query: { dry_run: dryRun } },
      body: file as unknown as string,
      bodySerializer: (body) => body as unknown as BodyInit,
      headers: { "Content-Type": "application/octet-stream" },
    }),
  );

export const createTaxProfile = (orgId: string, body: TaxProfileIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/tax-profiles", { params: orgPath(orgId), body }));

export const updateTaxProfile = (orgId: string, id: string, body: TaxProfilePatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/tax-profiles/{profile_id}", { params: { path: { org_id: orgId, profile_id: id } }, body }));

export const deleteTaxProfile = (orgId: string, id: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/tax-profiles/{profile_id}", { params: { path: { org_id: orgId, profile_id: id } } }));

export const createPayoutSchedule = (orgId: string, body: PayoutScheduleIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/payout-schedules", { params: orgPath(orgId), body }));

export const deletePayoutSchedule = (orgId: string, id: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/payout-schedules/{schedule_id}", { params: { path: { org_id: orgId, schedule_id: id } } }));

export const setInventorySettings = (orgId: string, body: InventorySettingsIn) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/settings/inventory", { params: orgPath(orgId), body }));
