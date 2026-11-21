// Oylik hisobot (M14, B7.3; ADR-065): hisob varag'i (F3 → F12) oldingi oy bilan, "Buyurtmadan sof foydagacha" (F49), eng foydali va
// zarardagi SKU'lar, Uzum va o'z xarajatlari toifalar bo'yicha, tovardagi pul (F29). Hamma raqam API'dan (`/reports/monthly`, Foyda
// sahifasi bilan bir hisob): bu yerda hisoblanmaydi (tamoyil 4). Chop etiladi va brauzerda PDF qilib saqlanadi (chop etish uslubi).
// Oy tugamagan yoki Jarayondagi buyurtma qolgan bo'lsa — "Dastlabki" (nechta buyurtma va qancha summa hali jarayonda).
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, monthlyReportQuery } from "../../app/query";
import { Badge, Banner, Button, DataTable, Skeleton, type Column } from "../../components/ui";
import type { MonthlyReport } from "../../lib/api/types";
import { addMonths, todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { rowLabel } from "../home/model";
import { Flow } from "../home/KpiSummary";

type Row = MonthlyReport["rows"][number];
type Sku = MonthlyReport["top"][number];

export function ReportsPage() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const [month, setMonth] = useState<string | null>(null);
  const query = useQuery(monthlyReportQuery(org.id, month));
  const data = query.data;
  const shown = data?.month ?? month;
  const thisMonth = `${todayTashkent().slice(0, 7)}-01`;
  const move = (delta: number) => shown && setMonth(addMonths(shown, delta));
  const ledger: Column<Row>[] = [
    { key: "name", header: t("reports.col.row"), mobile: true, render: (r) => rowLabel(r.code, t) },
    { key: "amount", header: t("reports.col.amount"), numeric: true, mobile: true, render: (r) => f.money(r.amount) },
    { key: "share", header: t("reports.col.share"), numeric: true, render: (r) => (r.share_of_revenue === null ? "—" : f.percent(r.share_of_revenue)) },
    { key: "prev", header: t("reports.col.previous"), numeric: true, render: (r) => f.money(r.previous) },
    { key: "diff", header: t("reports.col.diff"), numeric: true, render: (r) => f.money(r.diff) },
  ];
  const skuCols = (net: string): Column<Sku>[] => [
    { key: "title", header: "SKU", mobile: true, render: (s) => s.title ?? s.product_title ?? "—" },
    { key: "units", header: t("reports.col.units"), numeric: true, render: (s) => f.number(s.units) },
    { key: "revenue", header: t("terms.revenue"), numeric: true, render: (s) => f.money(s.revenue) },
    { key: "net", header: net, numeric: true, mobile: true, render: (s) => <strong>{f.money(s.net_profit)}</strong> },
  ];
  const categories = (map: Record<string, string>, label: (k: string) => string) =>
    Object.entries(map)
      .filter(([, v]) => Number(v) !== 0)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .map(([k, v]) => (
        <li key={k}>
          <span>{label(k)}</span>
          <span className="num">{f.money(v)}</span>
        </li>
      ));
  return (
    <section className="report">
      <header className="report__head">
        <div className="page-title">
          <h1 className="h2">{data ? t("reports.title", { month: f.month(data.month) }) : t("reports.titleShort")}</h1>
          {data && <Badge tone={data.status === "final" ? "positive" : "warning"}>{t(`reports.status.${data.status}`)}</Badge>}
        </div>
        <div className="report__tools no-print">
          <div className="goals__month" role="group" aria-label={t("reports.month")}>
            <Button variant="ghost" size="sm" aria-label={t("reports.prev")} onClick={() => move(-1)} disabled={!shown}>
              ‹
            </Button>
            <strong data-testid="report-month">{shown ? f.month(shown) : ""}</strong>
            <Button variant="ghost" size="sm" aria-label={t("reports.next")} onClick={() => move(1)} disabled={!shown || shown >= thisMonth}>
              ›
            </Button>
          </div>
          <Button icon={<Printer size={16} aria-hidden />} onClick={() => window.print()} disabled={!data}>
            {t("reports.print")}
          </Button>
        </div>
      </header>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={6} />
      ) : (
        <>
          <p className="caption">{t("reports.period", { start: f.date(data.period.start), end: f.date(data.period.end), previous: f.month(data.previous.start) })}</p>
          {data.status === "preliminary" && (
            <Banner tone="warning" title={t("reports.preliminary")}>
              {!data.month_over && <p>{t("reports.notOver")}</p>}
              {data.processing_lines > 0 && <p>{t("reports.processing", { n: data.processing_lines, sum: f.money(data.processing_revenue) })}</p>}
            </Banner>
          )}
          <dl className="report__kpis" aria-label={t("reports.kpis")}>
            <div>
              <dt>{t("terms.revenue")}</dt>
              <dd data-testid="report-revenue">{f.money(data.statement.revenue)}</dd>
            </div>
            <div>
              <dt>{t("terms.netProfit")}</dt>
              <dd data-testid="report-profit" className={Number(data.statement.net_profit) < 0 ? "ui-text--negative" : "ui-text--positive"}>
                {f.money(data.statement.net_profit)}
              </dd>
            </div>
            <div>
              <dt>{t("terms.margin")}</dt>
              <dd>{data.statement.margin === null ? "—" : f.percent(data.statement.margin)}</dd>
            </div>
            <div>
              <dt>{t("terms.roi")}</dt>
              <dd>{data.statement.roi === null ? "—" : f.percent(data.statement.roi)}</dd>
            </div>
          </dl>
          <section aria-labelledby="report-ledger">
            <h2 id="report-ledger" className="h3">
              {t("reports.ledger")}
            </h2>
            <DataTable caption={t("reports.ledger")} density="compact" columns={ledger} rows={data.rows} rowKey={(r) => r.code} empty={t("reports.empty")} />
          </section>
          <Flow steps={data.flow} />
          <div className="report__pair">
            <section aria-labelledby="report-top">
              <h2 id="report-top" className="h3">
                {t("reports.top")}
              </h2>
              <DataTable caption={t("reports.top")} density="compact" columns={skuCols(t("terms.netProfit"))} rows={data.top} rowKey={(s) => s.sku_id} empty={t("reports.empty")} />
            </section>
            <section aria-labelledby="report-bottom">
              <h2 id="report-bottom" className="h3">
                {t("reports.bottom")}
              </h2>
              <DataTable caption={t("reports.bottom")} density="compact" columns={skuCols(t("terms.netProfit"))} rows={data.bottom} rowKey={(s) => s.sku_id} empty={t("reports.noLoss")} />
            </section>
          </div>
          <div className="report__pair">
            <section aria-labelledby="report-uzum">
              <h2 id="report-uzum" className="h3">
                {t("reports.uzumExpenses")}
              </h2>
              <ul className="report__list">{categories(data.statement.uzum_expenses, (k) => t(`home.expense.${k}`, { defaultValue: k }))}</ul>
              <p className="report__total">
                <span>{t("reports.total")}</span> <strong className="num">{f.money(data.statement.uzum_total)}</strong>
              </p>
            </section>
            <section aria-labelledby="report-own">
              <h2 id="report-own" className="h3">
                {t("reports.ownExpenses")}
              </h2>
              <ul className="report__list">{categories(data.statement.own_expenses, (k) => k)}</ul>
              <p className="report__total">
                <span>{t("reports.total")}</span> <strong className="num">{f.money(data.statement.own_total)}</strong>
              </p>
            </section>
          </div>
          <section aria-labelledby="report-money">
            <h2 id="report-money" className="h3">
              {t("reports.frozen")}
            </h2>
            <p>
              <strong className="num" data-testid="report-frozen">
                {f.money(data.frozen_money)}
              </strong>{" "}
              <span className="caption">{t("reports.frozenNote", { transit: f.money(data.in_transit_value) })}</span>
            </p>
          </section>
        </>
      )}
    </section>
  );
}
