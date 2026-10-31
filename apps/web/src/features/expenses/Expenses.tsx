// Xarajatlar (M8, B4.5): Uzum xarajatlari (F9 — toifalar, oylar, jarimalar, ro'yxat) va o'z xarajatlarim (F10 — bir
// martalik, amortizatsiya, takroriy; qo'shish/tahrirlash/o'chirish). Bo'lim (`tab`) — URL'da. Hamma raqam API'dan.
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, expensesQuery, meQuery } from "../../app/query";
import { expensesSearch } from "../../app/search";
import { Banner, Button, Skeleton } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";
import { OwnExpenses } from "./OwnExpenses";
import { UzumExpenses } from "./UzumExpenses";

const TABS = ["uzum", "own"] as const;

export function Expenses() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  const navigate = useNavigate();
  const tab = expensesSearch(useSearch({ strict: false }) as Record<string, unknown>).section ?? "uzum";
  const params = useMemo(
    () => ({ shops: filters.shops, start: filters.range.start, end: filters.range.end }),
    [filters.shops, filters.range.start, filters.range.end],
  );
  const query = useQuery(expensesQuery(org.id, params));
  const setTab = (next: (typeof TABS)[number]) =>
    void navigate({ to: "/expenses", search: (prev) => ({ ...prev, section: next === "own" ? ("own" as const) : undefined }), replace: true });
  return (
    <section className="expenses">
      <header className="orders__head">
        <h1 className="h2">{t("expenses.title", { period: f.period(params.start, params.end) })}</h1>
      </header>
      <div role="tablist" aria-label={t("expenses.tabsLabel")} className="orders-tabs">
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`expenses-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="expenses-panel"
            className={cx("orders-tab", tab === id && "is-active")}
            onClick={() => setTab(id)}
          >
            {t(`expenses.tabs.${id}`)}
          </button>
        ))}
      </div>
      <div id="expenses-panel" role="tabpanel" aria-labelledby={`expenses-tab-${tab}`} className="expenses__panel">
        {query.isError ? (
          <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
        ) : !query.data ? (
          <Skeleton label={t("common.loading")} lines={8} />
        ) : tab === "uzum" ? (
          <UzumExpenses orgId={org.id} params={params} data={query.data} />
        ) : (
          <OwnExpenses orgId={org.id} params={params} data={query.data} canManage={org.role === "owner" || org.role === "manager"} />
        )}
      </div>
    </section>
  );
}
