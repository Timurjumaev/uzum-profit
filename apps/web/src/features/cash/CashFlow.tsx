// "Pul oqimi" (M11, F38; B5.7): Uzum sizga qaysi kuni qancha to'laydi. Yechishga tayyor summa, kutilgan to'lovlar
// (jadval Sozlamalarda, qoidalar ma'lumotnomadan — kodga qotirilmagan), topshirilmagan sotuvlar (sana noma'lum).
// Hammasi API'dan (`/payouts/forecast`): bu yerda hisoblanmaydi (tamoyil 4). Jarayondagi sotuvlar — "Taxminiy".
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, payoutForecastQuery } from "../../app/query";
import { Badge, Banner, DataTable, EmptyState, Kpi, Skeleton, type Column } from "../../components/ui";
import type { PayoutEvent } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

export function CashFlow() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const query = useQuery(payoutForecastQuery(org.id));
  const data = query.data;
  const feeNote = !data || data.fee_pct === null ? undefined : t("cash.feeNote", { fee: f.percent(String(Number(data.fee_pct) / 100)) });
  const columns: Column<PayoutEvent>[] = [
    {
      key: "date",
      header: t("cash.col.date"),
      mobile: true,
      render: (e) => (
        <span className="cash-date">
          <strong>{f.date(e.expected)}</strong>
          <span className="caption">{t("cash.latest", { date: f.date(e.latest) })}</span>
        </span>
      ),
    },
    { key: "gross", header: t("cash.col.gross"), numeric: true, render: (e) => f.money(e.gross) },
    { key: "fee", header: t("cash.col.fee"), numeric: true, render: (e) => f.money(e.fee) },
    { key: "net", header: t("cash.col.net"), numeric: true, mobile: true, render: (e) => <strong>{f.money(e.net)}</strong> },
    { key: "state", header: t("cash.col.state"), mobile: true, render: (e) => (e.estimated ? <Badge tone="warning">{t("cash.estimated")}</Badge> : <Badge tone="positive">{t("cash.sure")}</Badge>) },
  ];
  return (
    <section className="cash">
      <header className="cash__head">
        <h1 className="h2">{t("cash.title")}</h1>
        {data && <p className="caption">{t("cash.rules", { lag: data.rules.lag_days, fee: f.percent(String(Number(data.rules.urgent_fee_pct) / 100)) })}</p>}
      </header>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={4} />
      ) : data.schedule === null ? (
        <EmptyState
          title={t("cash.noSchedule")}
          text={t("cash.noScheduleText")}
          action={
            <Link to="/settings" className="ui-btn ui-btn--primary ui-btn--md">
              {t("cash.toSettings")}
            </Link>
          }
        />
      ) : (
        <>
          <div className="cash__kpis">
            <Kpi label={t("cash.kpi.available")} value={f.money(data.available)} note={t("cash.kpi.availableNote")} />
            <Kpi label={t("cash.kpi.next")} value={data.events[0] ? f.money(data.events[0].net) : "—"} note={data.events[0] ? f.date(data.events[0].expected) : t("cash.kpi.nextNone")} />
            <Kpi label={t("cash.kpi.unknown")} value={f.money(data.unknown_date)} note={t("cash.kpi.unknownNote")} />
            <Kpi label={t("cash.kpi.schedule")} value={t(`settings.payout.kind.${data.schedule as "daily" | "weekly" | "biweekly" | "monthly"}`)} note={feeNote} />
          </div>
          <Banner tone="info" title={t("cash.caveat")} />
          {data.events.length === 0 ? <EmptyState title={t("cash.empty")} text={t("cash.emptyText")} /> : <DataTable caption={t("cash.table")} columns={columns} rows={data.events} rowKey={(e) => e.expected} mobileList />}
        </>
      )}
    </section>
  );
}
