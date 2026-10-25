// Navigatsiya xaritasi (04 §7.1): sidebar, pastki tab bar va Ctrl+K bitta ro'yxatdan oladi. Marshrutlar — 03 §9.
// Sahifalari hali yo'q bo'limlar (B4+) "qurilmoqda" sahifasiga olib boradi — karkas B4 da o'zgarmaydi.
import {
  Activity,
  Banknote,
  FileText,
  LayoutDashboard,
  Package,
  ReceiptText,
  Settings,
  ShoppingCart,
  TrendingUp,
  Wallet,
  Warehouse,
  type LucideIcon,
} from "lucide-react";

export type NavKey =
  | "home"
  | "pnl"
  | "products"
  | "orders"
  | "expenses"
  | "purchases"
  | "inventory"
  | "cash"
  | "reports"
  | "status"
  | "settings";

export type NavTo = "/" | "/pnl" | "/products" | "/orders" | "/expenses" | "/purchases" | "/inventory" | "/cash" | "/reports" | "/status" | "/settings";

export type NavItem = { key: NavKey; to: NavTo; icon: LucideIcon };

const item = (key: NavKey, to: NavTo, icon: LucideIcon): NavItem => ({ key, to, icon });

/** Sidebar yuqori guruhi (modullar). */
export const NAV_MAIN: readonly NavItem[] = [
  item("home", "/", LayoutDashboard),
  item("pnl", "/pnl", TrendingUp),
  item("products", "/products", Package),
  item("orders", "/orders", ReceiptText),
  item("expenses", "/expenses", Wallet),
  item("purchases", "/purchases", ShoppingCart),
  item("inventory", "/inventory", Warehouse),
  item("cash", "/cash", Banknote),
  item("reports", "/reports", FileText),
];

/** Sidebar pastki guruhi (chiziqdan keyin). */
export const NAV_BOTTOM: readonly NavItem[] = [item("status", "/status", Activity), item("settings", "/settings", Settings)];

export const NAV_ALL: readonly NavItem[] = [...NAV_MAIN, ...NAV_BOTTOM];

/** Mobil tab bar (04 §7.1): Asosiy · Foyda · Ombor · Xaridlar · Yana. */
export const TAB_KEYS: readonly NavKey[] = ["home", "pnl", "inventory", "purchases"];

export const NAV_TABS: readonly NavItem[] = TAB_KEYS.map((key) => NAV_ALL.find((n) => n.key === key)!);

/** "Yana" ichidagi bo'limlar — tab bar'ga sig'magani. */
export const NAV_MORE: readonly NavItem[] = NAV_ALL.filter((n) => !TAB_KEYS.includes(n.key));

/** Joriy yo'l shu bo'limga tegishlimi ("/" — faqat aniq; "/products/12" — "/products" ga ham). */
export function isActivePath(pathname: string, to: NavTo): boolean {
  if (to === "/") return pathname === "/";
  return pathname === to || pathname.startsWith(`${to}/`);
}
