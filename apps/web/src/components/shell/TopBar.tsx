// TopBar (04 §7.1): do'kon, davr, solishtirish (filtrlar URL'da — `app/filters`; faqat sahifa ishlatadiganlari — `pageFilters`), o'ngda — SyncIndicator, tez o'tish
// (Ctrl+K) va foydalanuvchi menyusi. Mobilda ixcham: do'kon, davr, qidiruv, yangilik belgisi (solishtirish va
// hisob — "Yana" panelida).
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { pageFilters, useFilters } from "../../app/filters";
import { shopsQuery } from "../../app/query";
import { DateRangePicker } from "../ui";
import { CompareMenu } from "./CompareMenu";
import { shortcutLabel } from "./CommandPalette";
import { ShopFilter } from "./ShopFilter";
import { SyncIndicator } from "./SyncIndicator";
import { UserMenu, type Account } from "./UserMenu";

export type TopBarProps = { orgId: string | null; account: Account; onSearch: () => void };

export function TopBar({ orgId, account, onSearch }: TopBarProps) {
  const { t } = useTranslation();
  const { filters, setFilters } = useFilters();
  const { pathname } = useLocation();
  const kinds = pageFilters(pathname); // sahifa ishlatmaydigan filtr ko'rsatilmaydi
  const shops = useQuery({ ...shopsQuery(orgId ?? ""), enabled: orgId !== null });
  // "Hammasi" davri eng birinchi sotuvdan boshlanadi (tanlangan do'konlar bo'yicha).
  const first = useMemo(() => {
    const days = (shops.data ?? [])
      .filter((s) => filters.shops.length === 0 || filters.shops.includes(s.id))
      .map((s) => s.first_sale_on?.slice(0, 10))
      .filter((d): d is string => Boolean(d))
      .sort();
    return days[0];
  }, [shops.data, filters.shops]);
  return (
    <header className="topbar">
      <div className="topbar__filters" role="group" aria-label={t("shell.filters")}>
        {orgId && kinds.has("shop") && <ShopFilter orgId={orgId} selected={filters.shops} onChange={(shops) => setFilters({ shops })} />}
        {kinds.has("range") && <DateRangePicker value={filters.range} first={first} onChange={(range) => setFilters({ range })} />}
        {orgId && kinds.has("compare") && <CompareMenu value={filters.compare} onChange={(compare) => setFilters({ compare })} />}
        {kinds.size === 0 && <span className="caption topbar__scope">{t("shell.orgWide")}</span>}
      </div>
      <div className="topbar__tools">
        {orgId && <SyncIndicator orgId={orgId} />}
        <button type="button" className="ui-btn ui-btn--ghost ui-btn--md topbar__search" onClick={onSearch} aria-haspopup="dialog" aria-keyshortcuts="Control+K Meta+K">
          <Search size={16} aria-hidden />
          <span className="ui-visually-hidden">{t("shell.search")}</span>
          <kbd className="topbar__kbd">{shortcutLabel()}</kbd>
        </button>
        <span className="topbar__account">
          <UserMenu account={account} />
        </span>
      </div>
    </header>
  );
}
