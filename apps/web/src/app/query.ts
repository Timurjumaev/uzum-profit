// Server holati (03 §9): TanStack Query, staleTime 60 s. 4xx qayta so'ralmaydi (ruxsat yoki kiritish masalasi),
// tarmoq/5xx/429 — 2 marta. Sessiya tugasa (401) — kirish sahifasiga (`onUnauthorized`).
import { MutationCache, QueryCache, QueryClient, queryOptions } from "@tanstack/react-query";

import { api, ApiError, CSRF_HEADER, unwrap, type Problem } from "../lib/api/client";
import type { ComponentIn, ComponentPatch, ShipmentIn, ShipmentPatch, ItemLinkIn, LineIn, LinePatch, OwnExpenseIn, OwnExpensePatch, PurchaseIn, PurchasePatch, QuickPurchaseIn, SupplyState, TrackedIn, BoxIn, SharesIn, CountIn, SplitIn, TransferIn, DispatchIn, ResolveIn, ShortagePatch, StockMoveIn, TaxProfileIn, TaxProfilePatch, PayoutScheduleIn, InventorySettingsIn, AlertsIn, NotificationSettingsIn, OpeningIn, GoalIn, CostPreview, CostChangeIn } from "../lib/api/types";

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
export type ReportParams = { shops: string[]; start: string; end: string; lastYear?: boolean };

const reportQuery = (p: ReportParams) => ({ start: p.start, end: p.end, shop: p.shops.length > 0 ? p.shops : undefined });
/** Solishtirish (B5.6): faqat Bosh sahifa va Foyda — "o'tgan yil shu davri"; aks holda oldingi shu uzunlikdagi davr. */
const compareQuery = (p: ReportParams) => ({ ...reportQuery(p), compare: p.lastYear ? ("last_year" as const) : undefined });

/** Bosh sahifa (M4): hisob varag'i, davr chizig'i, kunlik grafik, TOP/zarar SKU, ko'rsatkichlar, "Diqqat talab qiladi". */
export const dashboardQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "dashboard", p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/dashboard", { params: { path: { org_id: orgId }, query: compareQuery(p) } })),
  });

/** Foyda va zarar (M5): hisob varag'i (oldingi davr bilan), kesim ustunlari (`view`), F16, F40. */
export const pnlQuery = (orgId: string, p: ReportParams, view: "month" | "shop" | "sku") =>
  queryOptions({
    queryKey: ["orgs", orgId, "pnl", view, p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/pnl", { params: { path: { org_id: orgId }, query: { ...compareQuery(p), view } } })),
  });

/** Drill-down: hisobga kiradigan sotuv qatorlari — Yakunlangan + Jarayonda (ADR-036; P&L qatorlari yig'indisi shulardan), bitta sahifa (ADR-054, B5.0d). */
export const drillSalesQuery = (orgId: string, p: ReportParams, page: number, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "drill", "sales", p, page, size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/sales", {
          params: { path: { org_id: orgId }, query: { ...reportQuery(p), counted: true, limit: size, page } },
        }),
      ),
  });

/** Bitta Uzum toifasi xarajatlari (yoki hamma toifa — `category: null`), bitta sahifa (ADR-054); `own_items` — hamma o'z xarajati. */
export const expensesPage = (orgId: string, p: ReportParams, category: string | null, page = 1, size = 50) =>
  unwrap(
    api.GET("/api/v1/orgs/{org_id}/expenses", {
      params: { path: { org_id: orgId }, query: { ...reportQuery(p), category, limit: size, page } },
    }),
  );

export const drillExpensesQuery = (orgId: string, p: ReportParams, category: string, page: number, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "drill", "uzum", category, p, page, size],
    queryFn: () => expensesPage(orgId, p, category, page, size),
  });

// --- Mahsulotlar (M6, B4.3) ---------------------------------------------------------------------------------------

export type SkuListParams = { q?: string; sort?: string; label?: string; abc?: string; xyz?: string; page?: number; size?: number };

/** SKU jadvali, bitta sahifa (ADR-054: `page` 1 dan, `limit` 20/50/100); `placeholderData` bilan sahifa almashganda jadval yo'qolmaydi. */
export const skusQuery = (orgId: string, p: ReportParams, l: SkuListParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "skus", p, l],
    queryFn: () =>
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
              xyz: l.xyz as "X" | undefined,
              limit: l.size ?? 50,
              page: l.page ?? 1,
            },
          },
        }),
      ),
  });

/** SKU sahifasi: shu davr hisobi, kunlik tarix, lotlar, qaytish sabablari, kalkulyator boshlang'ich qiymatlari. */
export const skuQuery = (orgId: string, skuId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "sku", skuId, p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/skus/{sku_id}", { params: { path: { org_id: orgId, sku_id: skuId }, query: reportQuery(p) } })),
  });

export type CalculatorInput = {
  price_cny: string;
  price: string;
  commission_pct: string;
  qty: string;
} & Partial<
  Record<
    | "china_cny_total"
    | "weight_kg"
    | "length_cm"
    | "width_cm"
    | "height_cm"
    | "cargo_usd_per_kg"
    | "cargo_usd_per_m3"
    | "extra_uzs"
    | "packaging_uzs"
    | "tax_pct"
    | "ads_pct"
    | "target_margin_pct"
    | "cny_rate"
    | "usd_rate",
    string
  >
>;

/** Kalkulyator boshlang'ich qiymatlari (B5.9): CBU kurslari, soliq taklifi, F37 tarifi. */
export const calculatorDefaultsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "calculator-defaults"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/calculator/defaults", { params: { path: { org_id: orgId } } })),
  });

/** Ilova ichidagi bildirishnomalar markazi (B6.3): foydalanuvchining oxirgi bildirishnomalari va o'qilmaganlar soni; har daqiqada yangilanadi. */
export const notificationsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "notifications"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/notifications", { params: { path: { org_id: orgId } } })),
    refetchInterval: 60_000,
  });

/** O'qilgan deb belgilash: `ids` yoki — berilmasa — hammasi. Javob — yangilangan ro'yxat. */
export const markNotificationsRead = (orgId: string, ids?: string[]) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/notifications/read", { params: { path: { org_id: orgId } }, body: { ids: ids ?? null } }));

/** Oylik hisobot (B7.3, M14): `month` — oyning istalgan kuni (bo'sh — joriy oy); hamma raqam mavjud hisobdan, oldingi kalendar oy bilan. */
export const monthlyReportQuery = (orgId: string, month: string | null) =>
  queryOptions({
    queryKey: ["orgs", orgId, "monthly-report", month],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/reports/monthly", { params: { path: { org_id: orgId }, query: month ? { month } : {} } })),
  });

/** Oylik maqsadlar va bajarilish (B5.8, M12; F59): `month` — oyning istalgan kuni (bo'sh — joriy oy). */
export const goalsQuery = (orgId: string, month: string | null) =>
  queryOptions({
    queryKey: ["orgs", orgId, "goals", month],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/goals", { params: { path: { org_id: orgId }, query: month ? { month } : {} } })),
  });

export const setGoal = (orgId: string, body: GoalIn) => unwrap(api.PUT("/api/v1/orgs/{org_id}/goals", { params: { path: { org_id: orgId } }, body }));

export const deleteGoal = (orgId: string, id: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/goals/{goal_id}", { params: { path: { org_id: orgId, goal_id: id } } }));

/** Kargo taklifi (B5.9): oldingi xaridlardagi haqiqiy kargo xarajatidan o'rtacha ($/kg, so'm/dona); tarif kiritilmaydi (ADR-061). */
export const cargoSuggestionQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "calculator-cargo-suggestion"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/calculator/cargo-suggestion", { params: { path: { org_id: orgId } } })),
  });

/** Saqlangan kalkulyator ssenariylari (B5.9-3): faqat kiritish; natija ochilganda joriy kurs/tarif bilan qayta hisoblanadi. */
export const scenariosQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "calculator-scenarios"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/calculator/scenarios", { params: { path: { org_id: orgId } } })),
  });

export const saveScenario = (orgId: string, name: string, inputs: Record<string, string>) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/calculator/scenarios", { params: { path: { org_id: orgId } }, body: { name, inputs } }));

export const deleteScenario = (orgId: string, id: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/calculator/scenarios/{scenario_id}", { params: { path: { org_id: orgId, scenario_id: id } } }));

/** Xariddan oldingi kalkulyator (M13): hisob serverda (tamoyil 4); kiritish o'zgargan sayin qayta so'raladi. */
export const calculatorQuery = (orgId: string, input: CalculatorInput) =>
  queryOptions({
    queryKey: ["orgs", orgId, "calculator", input],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/calculator", { params: { path: { org_id: orgId }, query: { ...input, qty: Number(input.qty) } } })),
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

/** Xarid tovari uchun tanlov: hamma SKU (holatidan qat'i nazar) va SKU'siz tovarlar. */
export const skuPickerQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "sku-picker"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/sku-picker", { params: { path: { org_id: orgId } } })),
    staleTime: 60_000,
  });

/** SKU ↔ tovar: mavjud tovarga, yangi tovar sifatida yoki ajratish (`mode: none`). */
export const linkItem = (orgId: string, skuId: string, body: ItemLinkIn) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/skus/{sku_id}/item", { params: { path: { org_id: orgId, sku_id: skuId } }, body }));

// --- Buyurtmalar (M7, B4.4) ---------------------------------------------------------------------------------------

/** Sotuv qatorlari ro'yxati (holat filtri bilan), bitta sahifa (ADR-054); `summary` — davr bo'yicha F17, F18. */
export const ordersQuery = (orgId: string, p: ReportParams, group: string | undefined, page: number | undefined, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "orders", p, group ?? null, page ?? 1, size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/sales", {
          params: {
            path: { org_id: orgId },
            query: { ...reportQuery(p), group: group as "completed" | undefined, limit: size, page: page ?? 1 },
          },
        }),
      ),
  });

/** Reklama tahlili (B5.5): turlar bo'yicha summa, kunlik DRR (F19), SKU ACOS va "reklama foydasini yeb qo'ygan" SKU (F58). */
export const adsQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "ads", p],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/ads", { params: { path: { org_id: orgId }, query: reportQuery(p) } })),
  });

/** Bekor va qaytish tahlili: ulushlar (F17, F18), kunlik trend, sabablar, SKU bo'yicha, qaytim saqlash xarajati. */
export const ordersAnalysisQuery = (orgId: string, p: ReportParams) =>
  queryOptions({
    queryKey: ["orgs", orgId, "orders-analysis", p],
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/orders/analysis", { params: { path: { org_id: orgId }, query: reportQuery(p) } })),
  });

// --- Xarajatlar (M8, B4.5) ----------------------------------------------------------------------------------------

/** Uzum xarajatlari ro'yxati, bitta sahifa (ADR-054; toifa filtri bilan). */
export const expensesListQuery = (orgId: string, p: ReportParams, category: string, page: number | undefined, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "expenses", "list", p, category, page ?? 1, size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/expenses", {
          params: { path: { org_id: orgId }, query: { ...reportQuery(p), category: category || null, limit: size, page: page ?? 1 } },
        }),
      ),
  });

/** Xarajatlar sahifasi: Uzum toifalari (F9), oylar, jarimalar, o'z xarajatlarim (F10) — bitta so'rov. */
export const expensesQuery = (orgId: string, p: ReportParams) =>
  queryOptions({ queryKey: ["orgs", orgId, "expenses", "summary", p], queryFn: () => expensesPage(orgId, p, null) });

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

/** Xaridlar ro'yxati, hammasi (Partiya yo'li va jonli tannarx bilan) — kargoga biriktirish uchun. */
export const purchasesQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "purchases", "list", "all"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/purchases", { params: { path: { org_id: orgId } } })),
  });

/** Xaridlar ro'yxati, bitta sahifa (ADR-054); holat filtri bilan (ADR-061: Yo'lda / Omborimda / Uzumda; bo'sh — hammasi). */
export const purchasesPageQuery = (orgId: string, states: SupplyState[], page: number | undefined, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "purchases", "list", states, page ?? 1, size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/purchases", {
          params: { path: { org_id: orgId }, query: { state: states.length > 0 ? states : undefined, limit: size, page: page ?? 1 } },
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

/** Tez xarid (ADR-061 §2): xarid, tovarlar va tovar summasi bitta so'rovda. */
export const createQuickPurchase = (orgId: string, body: QuickPurchaseIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/quick", { params: { path: { org_id: orgId } }, body }));

export const updatePurchase = (orgId: string, purchaseId: string, body: PurchasePatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/purchases/{purchase_id}", { params: purchasePath(orgId, purchaseId), body }));

export const deletePurchase = (orgId: string, purchaseId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/purchases/{purchase_id}", { params: purchasePath(orgId, purchaseId) }));

/** "Qayta buyurtma": qatorlar yangi qoralamaga (sanalar, qabul va komponentlarsiz). */
export const copyPurchase = (orgId: string, purchaseId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/copy", { params: purchasePath(orgId, purchaseId) }));

export const createLine = (orgId: string, purchaseId: string, body: LineIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/lines", { params: purchasePath(orgId, purchaseId), body }));

/** Bir nechta tovarni birdaniga qo'shish (hammasi yoki hech biri). */
export const createLines = (orgId: string, purchaseId: string, lines: LineIn[]) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/lines/bulk", { params: purchasePath(orgId, purchaseId), body: { lines } }));

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

// --- Kargolar (M9, B4.31, ADR-046): bitta kargo — ko'p xarid --------------------------------------------------------

export const shipmentsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "shipments", "list"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/shipments", { params: { path: { org_id: orgId } } })),
  });

/** Kargolar ro'yxati, bitta sahifa (B5.0d, ADR-054). */
export const shipmentsPageQuery = (orgId: string, page: number, size: number) =>
  queryOptions({
    queryKey: ["orgs", orgId, "shipments", "page", page, size],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/shipments", { params: { path: { org_id: orgId }, query: { limit: size, page } } })),
  });

/** Kargo puli jadvali (TM3, ADR-061 §3): kargo puli kutilayotgan xaridlar. */
export const cargoPoolQuery = (orgId: string, counted: boolean) =>
  queryOptions({
    queryKey: ["orgs", orgId, "purchases", "cargo-pool", counted],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/cargo-pool", { params: { path: { org_id: orgId }, query: { counted } } })),
  });

/** TM9.8: ro'yxatda "Keldi" (bir nechta xarid; ``arrived_on`` ``null`` — bekor qilish). */
export const markArrived = (orgId: string, body: { purchase_ids: string[]; arrived_on?: string | null }) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/arrived", { params: { path: { org_id: orgId } }, body }));

export const saveTrackedCargo = (orgId: string, body: TrackedIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/cargo-pool/tracked", { params: { path: { org_id: orgId } }, body }));

export const previewBoxShares = (orgId: string, body: SharesIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/cargo-pool/shares", { params: { path: { org_id: orgId } }, body }));

export const saveCargoBox = (orgId: string, body: BoxIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/cargo-pool/box", { params: { path: { org_id: orgId } }, body }));

export const setBoxShares = (orgId: string, shipmentId: string, componentId: string, fixed: Record<string, string>) =>
  unwrap(
    api.PUT("/api/v1/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}/purchase-shares", {
      params: { path: { org_id: orgId, shipment_id: shipmentId, component_id: componentId } },
      body: { fixed },
    }),
  );

/** Sanash (TM4, ADR-061 §6): kelgan son, brak, qadoq qo'shimchasi, sotuvchi qaytargan summa. */
export const countPurchase = (orgId: string, purchaseId: string, body: CountIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/count", { params: purchasePath(orgId, purchaseId), body }));

/** Xaridni ikkiga bo'lish (ADR-061 §6): ko'rsatilgan donalar yangi xaridga ("Yo'lda"). */
export const splitPurchase = (orgId: string, purchaseId: string, body: SplitIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/purchases/{purchase_id}/split", { params: purchasePath(orgId, purchaseId), body }));

/** Xarajat turlari lug'ati (ADR-061 §4): sotuvchining o'z turlari. */
export const costTypesQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "cost-types"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/cost-types", { params: { path: { org_id: orgId } } })),
  });

export const createCostType = (orgId: string, name: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/cost-types", { params: { path: { org_id: orgId } }, body: { name } }));

/** Kargo sahifasi: xaridlar (kargo ulushi bilan), xarajatlar, tovarlar (ulush har tovarga). */
export const shipmentQuery = (orgId: string, shipmentId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "shipments", "one", shipmentId],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/shipments/{shipment_id}", { params: { path: { org_id: orgId, shipment_id: shipmentId } } })),
  });

const shipmentPath = (orgId: string, shipmentId: string) => ({ path: { org_id: orgId, shipment_id: shipmentId } });

export const createShipment = (orgId: string, body: ShipmentIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/shipments", { params: { path: { org_id: orgId } }, body }));

export const updateShipment = (orgId: string, shipmentId: string, body: ShipmentPatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/shipments/{shipment_id}", { params: shipmentPath(orgId, shipmentId), body }));

export const deleteShipment = (orgId: string, shipmentId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/shipments/{shipment_id}", { params: shipmentPath(orgId, shipmentId) }));

export const createShipmentComponent = (orgId: string, shipmentId: string, body: ComponentIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/shipments/{shipment_id}/components", { params: shipmentPath(orgId, shipmentId), body }));

export const updateShipmentComponent = (orgId: string, shipmentId: string, componentId: string, body: ComponentPatch) =>
  unwrap(
    api.PATCH("/api/v1/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}", {
      params: { path: { org_id: orgId, shipment_id: shipmentId, component_id: componentId } },
      body,
    }),
  );

export const deleteShipmentComponent = (orgId: string, shipmentId: string, componentId: string) =>
  unwrap(
    api.DELETE("/api/v1/orgs/{org_id}/shipments/{shipment_id}/components/{component_id}", {
      params: { path: { org_id: orgId, shipment_id: shipmentId, component_id: componentId } },
    }),
  );

// --- Ombor (M10, B4.7) --------------------------------------------------------------------------------------------

/** To'lov prognozi (F38, B5.7): yechishga tayyor, kutilgan to'lovlar, sana noma'lum. */
export const payoutForecastQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "payouts", "forecast"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/payouts/forecast", { params: { path: { org_id: orgId } } })),
  });

/** Qoldiq jadvali: holat (server filtri), qidiruv, do'konlar; bitta sahifa (ADR-054). `totals` — butun tanlov bo'yicha. */
export const inventoryQuery = (orgId: string, shops: string[], l: { status?: string; ship?: boolean; q?: string; page?: number; size: number }) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", shops, l.status ?? null, l.ship ?? false, l.q ?? null, l.page ?? 1, l.size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/inventory", {
          params: {
            path: { org_id: orgId },
            query: { shop: shops.length > 0 ? shops : undefined, status: l.status as "critical" | undefined, ship: l.ship || undefined, q: l.q || undefined, limit: l.size, page: l.page ?? 1 },
          },
        }),
      ),
  });

/** Tovarning hisobdan chiqarish va tuzatish yozuvlari (yangisi birinchi). */
export const stockMovesQuery = (orgId: string, itemId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "stock-moves", itemId],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/items/{item_id}/stock-moves", { params: { path: { org_id: orgId, item_id: itemId } } })),
  });

export const createStockMove = (orgId: string, body: StockMoveIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/stock-moves", { params: { path: { org_id: orgId } }, body }));

/** F27 (B5.2): tovarning odatiy partiya hajmi (SKU orqali); `null` — o'chirish. */
export const setOrderBatch = (orgId: string, skuId: string, batch: number | null) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/skus/{sku_id}/order-batch", { params: { path: { org_id: orgId, sku_id: skuId } }, body: { batch } }));

/** Omborim (TM5, ADR-061 §7): SKU bo'yicha qoldiq, o'tkazish manbalari. */
export const warehouseQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "warehouse"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/warehouse", { params: { path: { org_id: orgId } } })),
  });

export const transferToSku = (orgId: string, body: TransferIn) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/warehouse/transfer", { params: { path: { org_id: orgId } }, body }));

export const cancelTransfer = (orgId: string, lineId: string) =>
  unwrap(api.DELETE("/api/v1/orgs/{org_id}/warehouse/transfers/{line_id}", { params: { path: { org_id: orgId, line_id: lineId } } }));

/** Uzumga jo'natish (TM6, ADR-061 §7): do'kon qoralamasi, jo'natmalar, bekor qilish, postavkani tanlash. */
export const dispatchDraftQuery = (orgId: string, shopId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "dispatch-draft", shopId],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/dispatches/draft", { params: { path: { org_id: orgId }, query: { shop_id: shopId } } })),
  });

export const dispatchesQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "dispatches"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/dispatches", { params: { path: { org_id: orgId } } })),
  });

export const createDispatch = (orgId: string, body: DispatchIn) => unwrap(api.POST("/api/v1/orgs/{org_id}/dispatches", { params: { path: { org_id: orgId } }, body }));

export const cancelDispatch = (orgId: string, id: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/dispatches/{dispatch_id}/cancel", { params: { path: { org_id: orgId, dispatch_id: id } } }));

export const linkDispatch = (orgId: string, id: string, invoiceId: string | null) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/dispatches/{dispatch_id}/link", { params: { path: { org_id: orgId, dispatch_id: id } }, body: { invoice_id: invoiceId } }));

export const dispatchExcelUrl = (orgId: string, id: string) => `/api/v1/orgs/${orgId}/dispatches/${id}/excel`;

/** TM9.1: jo'natmasiz postavkalar, qo'lda tanlash uchun hamma bog'lanmagan postavkalar. */
export const orphanInvoicesQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "dispatch-orphans"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/dispatches/orphans", { params: { path: { org_id: orgId } } })),
  });

export const dispatchInvoicesQuery = (orgId: string, id: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "dispatch-invoices", id],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/dispatches/{dispatch_id}/invoices", { params: { path: { org_id: orgId, dispatch_id: id } } })),
  });

export const orphanSent = (orgId: string, invoiceId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/dispatches/orphans/{invoice_id}/sent", { params: { path: { org_id: orgId, invoice_id: invoiceId } } }));

export const orphanNotMine = (orgId: string, invoiceId: string) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/dispatches/orphans/{invoice_id}/not-mine", { params: { path: { org_id: orgId, invoice_id: invoiceId } }, body: {} }));

/** Uzum qabulidagi farq (TM7, ADR-061 §8): farqlar va kamomad ro'yxati. */
export const receivingQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "receiving"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/receiving", { params: { path: { org_id: orgId } } })),
  });

export const resolveReceiving = (orgId: string, body: ResolveIn) => unwrap(api.POST("/api/v1/orgs/{org_id}/receiving/resolve", { params: { path: { org_id: orgId } }, body }));

/** TM9.2: "Men sanashda adashganman" / "Sonni oshirish" oqibati — oldindan (hech narsa saqlanmaydi). */
export const receivingPreviewQuery = (orgId: string, dispatchId: string, skuId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "inventory", "receiving-preview", dispatchId, skuId],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/receiving/preview", { params: { path: { org_id: orgId }, query: { dispatch_id: dispatchId, sku_id: skuId } } })),
  });

export const updateShortage = (orgId: string, id: string, body: ShortagePatch) =>
  unwrap(api.PATCH("/api/v1/orgs/{org_id}/receiving/shortages/{shortage_id}", { params: { path: { org_id: orgId, shortage_id: id } }, body }));

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

/** ADR-043: bekor va qaytarish ulushi ogohlantirish chegaralari (kasr, 0..1; `null` — o'chirish). */
export const setAlertSettings = (orgId: string, body: AlertsIn) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/settings/alerts", { params: orgPath(orgId), body }));

// --- Bildirishnomalar (B6.1, M15): har foydalanuvchining o'z sozlamasi ------------------------------------------

export const notificationSettingsQuery = (orgId: string) =>
  queryOptions({
    queryKey: ["orgs", orgId, "notifications", "settings"],
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/notifications/settings", { params: orgPath(orgId) })),
  });

export const setNotificationSettings = (orgId: string, body: NotificationSettingsIn) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/notifications/settings", { params: orgPath(orgId), body }));

export const telegramLink = (orgId: string) => unwrap(api.POST("/api/v1/orgs/{org_id}/notifications/telegram", { params: orgPath(orgId) }));

export const telegramUnlink = (orgId: string) => unwrap(api.DELETE("/api/v1/orgs/{org_id}/notifications/telegram", { params: orgPath(orgId) }));

// --- Boshlang'ich holat (F41, ADR-033) ---------------------------------------------------------------------------

export const openingKey = (orgId: string, start: string | null, shops: string[] = []) => ["orgs", orgId, "opening", start ?? "", ...shops] as const;

/** Boshlang'ich holat jadvali; `start` — boshqa boshlash sanasi uchun Uzum qoldig'i taklifi; `shops` — do'kon filtri. */
export const openingQuery = (orgId: string, start: string | null, shops: string[] = []) =>
  queryOptions({
    queryKey: openingKey(orgId, start, shops),
    queryFn: () =>
      unwrap(api.GET("/api/v1/orgs/{org_id}/opening", { params: { path: { org_id: orgId }, query: { ...(start ? { start } : {}), ...(shops.length ? { shop: shops } : {}) } } })),
  });

/** Tannarxni Excel orqali kiritish (B7.1): faylni to'g'ridan-to'g'ri tana qilib yuboradi (multipart emas), javob — ko'rib chiqish. */
export async function previewCosts(orgId: string, file: File): Promise<CostPreview> {
  let response: Response;
  try {
    response = await globalThis.fetch(
      new Request(new URL(`/api/v1/orgs/${orgId}/opening/costs/preview`, globalThis.location.origin).href, {
        method: "POST",
        body: file,
        credentials: "include",
        headers: { "Content-Type": file.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", [CSRF_HEADER]: "web" },
      }),
    );
  } catch {
    throw new ApiError(0, null);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body && typeof body === "object" ? (body as Partial<Problem>) : null, response.headers.get("X-Request-ID"));
  return body as CostPreview;
}

export const applyCosts = (orgId: string, changes: CostChangeIn[]) =>
  unwrap(api.POST("/api/v1/orgs/{org_id}/opening/costs/apply", { params: { path: { org_id: orgId } }, body: { changes } }));

export const saveOpening = (orgId: string, body: OpeningIn, shops: string[] = []) =>
  unwrap(api.PUT("/api/v1/orgs/{org_id}/opening", { params: { path: { org_id: orgId }, query: shops.length ? { shop: shops } : {} }, body }));
