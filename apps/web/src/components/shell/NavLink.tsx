// Navigatsiya havolasi: faol bo'lim `aria-current="page"` (marshrutlovchi o'zi qo'yadi), davr va do'kon filtrlari
// o'tishda saqlanadi (`search` — joriy qiymat).
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { cx } from "../ui/cx";
import type { NavItem } from "./nav";

export function NavLink({ item, className, onNavigate }: { item: NavItem; className?: string; onNavigate?: () => void }) {
  const { t } = useTranslation();
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      search={(prev) => prev}
      className={cx("nav-link", className)}
      activeProps={{ className: "is-active" }}
      activeOptions={{ exact: item.to === "/", includeSearch: false }}
      onClick={onNavigate}
    >
      <Icon size={20} aria-hidden />
      <span className="nav-link__label">{t(`nav.${item.key}`)}</span>
    </Link>
  );
}
