// Bosh sahifa (M4, ADR-037) — "bir qarashda": uch raqam (yakunlangan + kutilayotgan = jami sof foyda), davr chizig'i,
// "Diqqat talab qiladi", kunlik grafik (sof foyda yakunlangan va kutilayotgan qatlamlarda), KPI sarhisob (ADR-043:
// buyurtmadan sof foydagacha yo'l va yig'iladigan 4 guruh kartochka oldingi davr bilan), eng foydali 5 / zarar 5 SKU va
// tovardagi pul (tartib — ADR-057 Q10).
// Qatorma-qator hisob — Foyda sahifasida. Maket — 04 §7.2 (desktop) / §7.3 (mobil). Davr, do'kon va solishtirish —
// URL'da (`app/filters`), hamma raqam API'dan (`/dashboard`), bu yerda hisoblash yo'q.
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, dashboardQuery, meQuery, syncQuery } from "../../app/query";
import { Banner, Button, EmptyState, Skeleton } from "../../components/ui";
import { RevenueLimitBanner } from "../settings/RevenueLimit";
import { syncSummary } from "../../lib/sync";
import { Attention, DailyChart, Kpis, PeriodStrip, SkuLists } from "./Blocks";
import { KpiSummary } from "./KpiSummary";
import { attentionItems } from "./model";
import { Summary } from "./Summary";

export function Home() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  const params = useMemo(
    () => ({ shops: filters.shops, start: filters.range.start, end: filters.range.end }),
    [filters.shops, filters.range.start, filters.range.end],
  );
  const query = useQuery({ ...dashboardQuery(org.id, params), placeholderData: keepPreviousData });
  const sync = useQuery(syncQuery(org.id));

  const data = query.data;
  const summary = sync.data ? syncSummary(sync.data) : null;
  const syncIssues = sync.data ? sync.data.shops.filter((s) => s.active && !s.healthy).length : 0;
  const attention = useMemo(() => (data ? attentionItems(data.attention, syncIssues) : []), [data, syncIssues]);

  if (query.isError && !data) {
    return (
      <section className="home">
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  }
  if (!data) {
    return (
      <section className="home" aria-busy>
        <h1 className="ui-visually-hidden">{t("nav.home")}</h1>
        <Skeleton label={t("common.loading")} lines={8} />
      </section>
    );
  }

  const noSales = data.statement.lines === 0;
  const emptyState = summary?.state === "never" ? "never" : summary && summary.state !== "fresh" ? "partial" : "none";
  return (
    <section className="home" aria-busy={query.isPlaceholderData || undefined}>
      {filters.compare === "lastYear" && <Banner tone="info" title={t("home.lastYearSoon")} />}
      {/* F50 (B4.80): yillik tushum chegarasiga yaqin (≥ 80%) yoki oshgan — rejimni o'zgartirish vaqti. */}
      <RevenueLimitBanner
        limit={data.revenue_limit}
        action={
          <Link to="/settings" className="ui-btn ui-btn--secondary ui-btn--md">
            {t("settings.tax.limit.action")}
          </Link>
        }
      />
      {noSales && (
        <EmptyState
          title={t(`home.empty.${emptyState}`)}
          text={t(`home.empty.${emptyState}Text`)}
          action={
            emptyState === "none" ? undefined : (
              <Link to="/status" search={(prev) => prev} className="ui-btn ui-btn--secondary ui-btn--md">
                {t("home.empty.status")}
              </Link>
            )
          }
        />
      )}
      <Summary
        data={data}
        costAction={
          <Link to="/products" search={(prev) => prev} className="ui-btn ui-btn--secondary ui-btn--md">
            {t("home.coverage.action")}
          </Link>
        }
      />
      {/* ADR-057 Q10 (B4.72): uch raqam → davr → Diqqat talab qiladi → kunlik grafik → zinapoya va KPI guruhlari (yig'iladi)
          → TOP/zarar → tovardagi pul. "Diqqat talab qiladi" telefonda yuqorida (avval 7-ekranda edi, audit D1). */}
      <PeriodStrip data={data} />
      <Attention items={attention} />
      <DailyChart data={data} />
      <KpiSummary data={data} />
      <SkuLists top={data.top} bottom={data.bottom} />
      <Kpis data={data} />
    </section>
  );
}
