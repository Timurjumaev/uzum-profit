// Sidebar (04 §7.1): 232 px, yig'ilganda 64 px (tanlov saqlanadi). Yig'ilganda yozuv ekran o'quvchi uchun qoladi,
// ko'rinishda ikon + `title`. 768–1023 px da har doim yig'ilgan (CSS).
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Logo } from "./Logo";
import { NavLink } from "./NavLink";
import { NAV_BOTTOM, NAV_MAIN, type NavItem } from "./nav";

function Group({ items, collapsed }: { items: readonly NavItem[]; collapsed: boolean }) {
  const { t } = useTranslation();
  return (
    <ul className="sidebar__group">
      {items.map((item) => (
        <li key={item.key} title={collapsed ? t(`nav.${item.key}`) : undefined}>
          <NavLink item={item} />
        </li>
      ))}
    </ul>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { t } = useTranslation();
  const Toggle = collapsed ? PanelLeftOpen : PanelLeftClose;
  const label = t(collapsed ? "nav.expand" : "nav.collapse");
  return (
    <aside className="sidebar" data-collapsed={collapsed || undefined}>
      <div className="sidebar__brand">
        <Logo />
        <span className="sidebar__name">{t("app.name")}</span>
      </div>
      <nav aria-label={t("nav.main")} className="sidebar__nav">
        <Group items={NAV_MAIN} collapsed={collapsed} />
        <Group items={NAV_BOTTOM} collapsed={collapsed} />
      </nav>
      <button type="button" className="ui-icon-btn sidebar__toggle" onClick={onToggle} aria-label={label} aria-pressed={collapsed} title={label}>
        <Toggle size={20} aria-hidden />
      </button>
    </aside>
  );
}
