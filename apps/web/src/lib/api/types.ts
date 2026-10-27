// API javob tiplari (03 §8): apps/api/openapi.json dan generatsiya — `pnpm --filter web api:types`.
// Qo'lda yozilmaydi; backend o'zgarsa CI farqni ko'rsatadi. Pul va nisbatlar — satr ("123456.00", "0.125000").
import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type ApiPaths = paths;
export type Statement = Schemas["StatementOut"];
export type PnlRow = Schemas["RowOut"];
export type Dashboard = Schemas["DashboardOut"];
export type Pnl = Schemas["PnlOut"];
export type Skus = Schemas["SkusOut"];
export type SkuRow = Schemas["SkuRowOut"];
export type Sales = Schemas["SalesOut"];
export type Sale = Schemas["SaleOut"];
export type Expenses = Schemas["ExpensesOut"];
export type Inventory = Schemas["InventoryOut"];
export type StockRow = Schemas["StockRowOut"];
export type Meta = Schemas["Meta"];
export type Waiver = Schemas["WaiverOut"];
export type WaiverSuggestion = Schemas["SuggestionOut"];
export type FeeWaivers = Schemas["FeeWaiversOut"];
export type WaiverIn = Schemas["WaiverIn"];
export type SkuDetail = Schemas["SkuDetailOut"];
export type SkuDay = Schemas["SkuDayOut"];
export type SkuLot = Schemas["LotOut"];
export type SkuCalcDefaults = Schemas["CalcDefaultsOut"];
export type UnitCalc = Schemas["UnitCalcOut"];
export type ItemOption = Schemas["ItemOut"];
export type LinkedItem = Schemas["LinkedItemOut"];
export type ItemLinkIn = Schemas["ItemLinkIn"];
export type OrdersAnalysis = Schemas["OrdersAnalysisOut"];
export type OrdersSummary = Schemas["OrdersSummaryOut"];
export type OrdersDay = Schemas["OrdersDayOut"];
export type OrdersSkuShare = Schemas["OrdersSkuOut"];
export type OrdersCause = Schemas["OrdersCauseOut"];
