// Bekor va qaytish tahlili (M7): ulush (F17 / F18), topshirilgandan keyin bekor, qaytim saqlash xarajati, kunlik trend,
// sabablar (`returnCause`) va SKU bo'yicha jadval. Hamma raqam API'dan (`/orders/analysis`).
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { ordersAnalysisQuery, type ReportParams } from "../../app/query";
import { LineBarChart } from "../../components/charts";
import { Banner, Button, DataTable, EmptyState, FormulaPopover, Kpi, Skeleton, type Column } from "../../components/ui";
import type { OrdersCause, OrdersSkuShare } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Props = { orgId: string; params: ReportParams; kind: "cancel" | "returns" };

export function Analysis({ orgId, params, kind }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useQuery(ordersAnalysisQuery(orgId, params));
  if (query.isError) {
    return <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />;
  }
  if (!query.data) return <Skeleton label={t("common.loading")} lines={8} />;

  const { summary: s, daily, by_sku: skus } = query.data;
  const cancel = kind === "cancel";
  const causes = cancel ? query.data.cancel_causes : query.data.return_causes;
  const formula = cancel ? "cancel" : "returns";
  const share = (value: string | null) => (value === null ? "—" : f.percent(value));
  const help = (
    <FormulaPopover
      metric={t(`orders.${kind}.share`)}
      code={t(`home.formula.${formula}.code`)}
      formula={t(`home.formula.${formula}.formula`)}
      source={t(`home.formula.${formula}.source`)}
    />
  );
  if (s.units + s.canceled + s.returns === 0) return <EmptyState title={t("orders.empty")} text={t("orders.emptyText")} />;

  const unitsOf = (r: OrdersSkuShare) => (cancel ? r.canceled : r.returns);
  const skuColumns: Column<OrdersSkuShare>[] = [
    {
      key: "sku",
      header: t("orders.col.sku"),
      render: (r) =>
        r.sku_id ? (
          <Link to="/products/$skuId" params={{ skuId: r.sku_id }} search={(prev) => ({ shop: prev.shop, from: prev.from, to: prev.to, cmp: prev.cmp })}>
            {r.title ?? t("orders.unnamed")}
          </Link>
        ) : (
          t("orders.unlinked")
        ),
    },
    { key: "units", header: t("orders.col.sold"), numeric: true, render: (r) => f.number(r.units) },
    { key: "count", header: t(`orders.${kind}.units`), numeric: true, render: (r) => f.number(unitsOf(r)) },
    { key: "share", header: t(`orders.${kind}.share`), numeric: true, render: (r) => share(cancel ? r.cancel_share : r.return_share), help },
  ];
  const causeColumns: Column<OrdersCause>[] = [
    { key: "cause", header: t("orders.col.cause"), render: (r) => r.cause ?? t("orders.noCause") },
    { key: "units", header: t("orders.col.units"), numeric: true, render: (r) => f.number(r.units) },
  ];
  const x = daily.map((d) => d.day);
  const values = daily.map((d) => String(cancel ? d.canceled : d.returns));
  return (
    <div className="orders-analysis">
      <div className="orders-kpis">
        <Kpi label={t(`orders.${kind}.share`)} value={share(cancel ? s.cancel_share : s.return_share)} good="down" help={help} />
        <Kpi label={t(`orders.${kind}.units`)} value={f.number(cancel ? s.canceled : s.returns)} good="down" />
        {cancel ? (
          <Kpi
            label={t("orders.cancel.afterIssue")}
            value={f.number(s.canceled_after_issue)}
            good="down"
            note={s.after_issue_share === null ? undefined : t("orders.cancel.afterIssueNote", { share: f.percent(s.after_issue_share) })}
          />
        ) : (
          <Kpi label={t("orders.returns.storageCost")} value={f.money(s.return_storage_cost)} good="down" note={t("orders.returns.storageNote")} />
        )}
      </div>
      <LineBarChart title={t(`orders.${kind}.trend`)} x={x} unit="count" series={[{ key: kind, name: t(`orders.${kind}.units`), color: cancel ? 2 : 3, values }]} />
      <div className="orders-analysis__tables">
        <section aria-labelledby={`orders-causes-${kind}`}>
          <h2 id={`orders-causes-${kind}`} className="h3">
            {t(`orders.${kind}.causes`)}
          </h2>
          <DataTable caption={t(`orders.${kind}.causes`)} density="compact" columns={causeColumns} rows={causes} rowKey={(r) => r.cause ?? ""} empty={t("orders.noCauses")} />
        </section>
        <section aria-labelledby={`orders-skus-${kind}`}>
          <h2 id={`orders-skus-${kind}`} className="h3">
            {t("orders.bySku")}
          </h2>
          <DataTable
            caption={t("orders.bySku")}
            density="compact"
            columns={skuColumns}
            rows={skus.filter((r) => unitsOf(r) > 0)}
            rowKey={(r) => r.sku_id ?? "unlinked"}
            empty={t("orders.noSkus")}
          />
        </section>
      </div>
    </div>
  );
}
