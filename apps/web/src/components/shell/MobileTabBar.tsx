// Mobil tab bar (04 §7.1): Asosiy · Foyda · Ombor · Xaridlar · Yana. "Yana" — qolgan bo'limlar, solishtirish,
// ko'rinish va chiqish (pastdan chiqadigan panel). Bosish maydoni ≥ 44 px (04 §11).
import { useLocation } from "@tanstack/react-router";
import { Ellipsis } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { pageFilters, useFilters } from "../../app/filters";
import { CompareToggle, Drawer } from "../ui";
import { cx } from "../ui/cx";
import { NavLink } from "./NavLink";
import { isActivePath, NAV_MORE, NAV_TABS } from "./nav";
import { AccountPanel, type Account } from "./UserMenu";

export function MobileTabBar({ account }: { account: Account }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const { filters, setFilters } = useFilters();
  const moreActive = NAV_MORE.some((n) => isActivePath(pathname, n.to));
  return (
    <nav className="tabbar" aria-label={t("nav.mobile")}>
      <ul>
        {NAV_TABS.map((item) => (
          <li key={item.key}>
            <NavLink item={item} className="tabbar__link" />
          </li>
        ))}
        <li>
          <button type="button" className={cx("nav-link tabbar__link", moreActive && "is-active")} aria-haspopup="dialog" onClick={() => setOpen(true)}>
            <Ellipsis size={20} aria-hidden />
            <span className="nav-link__label">{t("nav.more")}</span>
          </button>
        </li>
      </ul>
      <Drawer open={open} onClose={() => setOpen(false)} title={t("nav.more")}>
        <ul className="more__list">
          {NAV_MORE.map((item) => (
            <li key={item.key}>
              <NavLink item={item} className="more__link" onNavigate={() => setOpen(false)} />
            </li>
          ))}
        </ul>
        {pageFilters(pathname).has("compare") && (
          <div className="more__section">
            <CompareToggle value={filters.compare} onChange={(compare) => setFilters({ compare })} />
          </div>
        )}
        <AccountPanel account={account} />
      </Drawer>
    </nav>
  );
}
