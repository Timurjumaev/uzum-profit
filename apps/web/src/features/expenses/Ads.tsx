// Reklama tahlili (B5.5, F19, F42, F58): Uzum yechgan reklama — turlar bo'yicha (Uzum kodi va uning o'z matni), kunlik DRR
// trendi, SKU bo'yicha ACOS va "reklama foydasini yeb qo'ygan" SKU'lar. Open API'da kampaniya, ko'rish va klik yo'q —
// ROMI va CTR ko'rsatilmaydi. Hamma raqam API'dan (`/ads`).
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { adsQuery, type ReportParams } from "../../app/query";
import { LineBarChart } from "../../components/charts";
import { Banner, Button, DataTable, EmptyState, FormulaPopover, Kpi, Skeleton, type Column } from "../../components/ui";
import type { Ads, AdsSku, AdsType } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

export function AdsAnalysis({ orgId, params }: { orgId: string; params: ReportParams }) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useQuery(adsQuery(orgId, params));
  if (query.isError) {
    return <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />;
  }
  if (!query.data) return <Skeleton label={t("common.loading")} lines={8} />;
  const d: Ads = query.data;
  if (Number(d.total) === 0 && d.by_type.length === 0) return <EmptyState title={t("expenses.ads.empty")} text={t("expenses.ads.emptyText")} />;

  const help = (key: string, metric: string) => (
    <FormulaPopover metric={metric} code={t(`expenses.ads.formula.${key}.code`)} formula={t(`expenses.ads.formula.${key}.formula`)} source={t(`expenses.ads.formula.${key}.source`)} />
  );
  const share = (v: string | null) => (v === null ? "—" : f.percent(v));
  const typeColumns: Column<AdsType>[] = [
    { key: "type", header: t("expenses.ads.col.type"), render: (r) => r.name ?? t("expenses.ads.noName") },
    { key: "code", header: t("expenses.ads.col.code"), render: (r) => r.code ?? "—" },
    { key: "amount", header: t("expenses.col.amount"), numeric: true, render: (r) => f.money(r.amount, { unit: false }) },
    { key: "share", header: t("expenses.col.share"), numeric: true, render: (r) => share(r.share) },
  ];
  const skuColumns = (title: string): Column<AdsSku>[] => [
    {
      key: "sku",
      header: title,
      render: (r) => (
        <Link to="/products/$skuId" params={{ skuId: r.sku_id }} search={(prev) => ({ shop: prev.shop, from: prev.from, to: prev.to, cmp: prev.cmp })}>
          {r.title ?? t("home.sku.unnamed")}
        </Link>
      ),
    },
    { key: "revenue", header: t("expenses.ads.col.revenue"), numeric: true, render: (r) => f.money(r.revenue, { unit: false }) },
    { key: "ads", header: t("expenses.ads.col.ads"), numeric: true, render: (r) => f.money(r.ads, { unit: false }) },
    { key: "acos", header: t("expenses.ads.col.acos"), numeric: true, render: (r) => share(r.acos), help: help("acos", t("expenses.ads.col.acos")) },
    {
      key: "net",
      header: t("expenses.ads.col.net"),
      numeric: true,
      render: (r) => <span className={Number(r.net_profit) < 0 ? "ui-text--negative" : undefined}>{f.money(r.net_profit, { unit: false })}</span>,
    },
  ];
  const x = d.daily.map((day) => day.day);
  const values = d.daily.map((day) => (day.drr === null ? null : String(Math.round(Number(day.drr) * 1000) / 10)));
  return (
    <div className="ads-analysis">
      <div className="orders-kpis">
        <Kpi label={t("expenses.ads.total")} value={f.money(d.total)} good="down" note={Number(d.estimated) > 0 ? t("expenses.ads.estimated", { amount: f.money(d.estimated) }) : undefined} />
        <Kpi label={t("expenses.ads.drr")} value={d.drr === null ? "—" : f.percent(d.drr)} good="down" help={help("drr", t("expenses.ads.drr"))} />
        <Kpi label={t("expenses.ads.revenue")} value={f.money(d.revenue)} />
      </div>
      <p className="caption">{t("expenses.ads.noRomi")}</p>
      <LineBarChart title={t("expenses.ads.trend")} x={x} unit="count" series={[{ key: "drr", name: t("expenses.ads.drrPct"), color: 4, kind: "line", values }]} />
      <section aria-labelledby="ads-types">
        <h2 id="ads-types" className="h3">
          {t("expenses.ads.byType")}
        </h2>
        <DataTable caption={t("expenses.ads.byType")} density="compact" columns={typeColumns} rows={d.by_type} rowKey={(r) => r.code ?? "none"} empty={t("expenses.ads.noTypes")} />
      </section>
      <section aria-labelledby="ads-eaten">
        <h2 id="ads-eaten" className="h3">
          {t("expenses.ads.eaten")} {help("eaten", t("expenses.ads.eaten"))}
        </h2>
        <p className="caption">{t("expenses.ads.eatenNote", { total: f.number(d.eaten_total) })}</p>
        <DataTable caption={t("expenses.ads.eaten")} density="compact" columns={skuColumns(t("expenses.ads.col.sku"))} rows={d.eaten} rowKey={(r) => r.sku_id} empty={t("expenses.ads.noEaten")} />
        {d.skipped > 0 && <p className="caption">{t("expenses.ads.skipped", { value: f.number(d.skipped) })}</p>}
      </section>
      <section aria-labelledby="ads-skus">
        <h2 id="ads-skus" className="h3">
          {t("expenses.ads.bySku")}
        </h2>
        <DataTable caption={t("expenses.ads.bySku")} density="compact" columns={skuColumns(t("expenses.ads.col.sku"))} rows={d.skus} rowKey={(r) => r.sku_id} empty={t("expenses.ads.noSkus")} />
      </section>
    </div>
  );
}
