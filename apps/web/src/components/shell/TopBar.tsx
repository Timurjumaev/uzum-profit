// TopBar (04 §7.1): do'kon, davr, solishtirish (filtrlar URL'da — `app/filters`), o'ngda — SyncIndicator, tez o'tish
// (Ctrl+K) va foydalanuvchi menyusi. Mobilda ixcham: do'kon, davr, qidiruv, yangilik belgisi (solishtirish va
// hisob — "Yana" panelida).
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useFilters } from "../../app/filters";
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
        {orgId && <ShopFilter orgId={orgId} selected={filters.shops} onChange={(shops) => setFilters({ shops })} />}
        <DateRangePicker value={filters.range} first={first} onChange={(range) => setFilters({ range })} />
        {orgId && <CompareMenu value={filters.compare} onChange={(compare) => setFilters({ compare })} />}
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
