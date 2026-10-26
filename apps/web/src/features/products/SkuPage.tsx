// SKU sahifasi (M6, B4.3): sarlavha (rasm, nom, Uzum sahifasiga havola), KPI'lar (har biri formula bilan), narx, foyda
// va sotuv tarixi, qoldiq tarixi, tannarx tarixi (tovar lotlari), qaytishlar sabablari, tovarga bog'lash va unit
// kalkulyator. Hamma raqam API'dan (`/skus/{id}`); me'yoriy foyda (F40) bonus davrida alohida, haqiqiy foyda o'zgarmaydi.
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, meQuery, shopsQuery, skuQuery } from "../../app/query";
import { LineBarChart } from "../../components/charts";
import type { Band } from "../../components/charts";
import { Badge, Banner, Button, DataTable, FormulaPopover, Kpi, ProductThumb, Skeleton, StatusPill, type Column } from "../../components/ui";
import type { SkuDetail, SkuLot } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { useKindLabel } from "../pnl/Waivers";
import { Calculator } from "./Calculator";
import { LinkItem } from "./LinkItem";
import { LABEL_TONE } from "./model";

export function SkuPage() {
  const { t } = useTranslation();
  const { skuId } = useParams({ strict: false }) as { skuId: string };
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const { filters } = useFilters();
  const params = useMemo(
    () => ({ shops: filters.shops, start: filters.range.start, end: filters.range.end }),
    [filters.shops, filters.range.start, filters.range.end],
  );
  const query = useQuery({ ...skuQuery(org.id, skuId, params), placeholderData: keepPreviousData });
  const back = (
    <Link to="/products" search={(prev) => ({ shop: prev.shop, from: prev.from, to: prev.to, cmp: prev.cmp })} className="sku__back">
      <ArrowLeft size={16} aria-hidden /> {t("products.back")}
    </Link>
  );
  if (query.isError && !query.data) {
    return (
      <section className="sku">
        {back}
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  }
  if (!query.data) {
    return (
      <section className="sku" aria-busy>
        {back}
        <h1 className="ui-visually-hidden">{t("nav.products")}</h1>
        <Skeleton label={t("common.loading")} lines={10} />
      </section>
    );
  }
  return (
    <section className="sku" aria-busy={query.isPlaceholderData || undefined}>
      {back}
      <Detail orgId={org.id} detail={query.data} canManage={org.role === "owner" || org.role === "manager"} />
    </section>
  );
}

function Detail({ orgId, detail, canManage }: { orgId: string; detail: SkuDetail; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shops = useQuery(shopsQuery(orgId));
  const kindLabel = useKindLabel();
  const { sku, statement: s } = detail;
  const name = sku.title ?? sku.product_title ?? t("home.sku.unnamed");
  const shop = shops.data?.find((x) => x.id === sku.shop_id);
  const waivers = detail.bonus.waivers.filter((w) => w.shop_id === null || w.shop_id === sku.shop_id);
  const { period } = detail.meta;

  const help = (key: string, metric: string) => (
    <FormulaPopover
      metric={metric}
      code={t(`home.formula.${key}.code`)}
      formula={t(`home.formula.${key}.formula`)}
      source={t(`home.formula.${key}.source`)}
      estimatedReason={key === "normative" ? t("home.formula.normative.estimated") : undefined}
    />
  );
  const percent = (v: string | null) => (v === null ? "—" : f.percent(v));
  const money = (v: string | null) => (v === null ? "—" : f.money(v));
  const uncovered = Number(sku.uncovered_share) > 0 ? t("home.kpis.uncovered", { share: f.percent(sku.uncovered_share) }) : undefined;
  return (
    <>
      <header className="sku__head">
        <ProductThumb src={sku.image_url} name={name} size={64} />
        <div className="sku__title">
          <h1 className="h2">{name}</h1>
          <p className="caption">
            {[sku.product_title && sku.title ? sku.product_title : null, sku.article, sku.barcode, shop ? (shop.alias ?? shop.name) : null].filter(Boolean).join(" · ")}
          </p>
          <p className="sku__badges">
            <StatusPill tone={LABEL_TONE[sku.label]}>{t(`products.label.${sku.label}`)}</StatusPill>
            <Badge>ABC: {sku.abc}</Badge>
            {sku.rank && <Badge>{t("products.rank", { value: sku.rank })}</Badge>}
            {detail.uzum_url && (
              <a href={detail.uzum_url} target="_blank" rel="noopener noreferrer" className="sku__ext">
                {t("products.openUzum")} <ExternalLink size={14} aria-hidden />
              </a>
            )}
          </p>
        </div>
      </header>
      <p className="caption">{t("products.sku.period", { period: f.period(period.start, period.end) })}</p>

      {waivers.map((w) => (
        <Banner key={w.id} tone="info" title={t("pnl.waivers.title", { reason: w.reason || t("pnl.waivers.noReason") })}>
          {t("products.sku.waiverText", { period: f.period(w.start_on, w.end_on), kinds: w.kinds.map(kindLabel).join(", ") })}
          {detail.bonus.unestimated_kinds.length > 0 && <> {t("products.bonus.unestimated", { kinds: detail.bonus.unestimated_kinds.map(kindLabel).join(", ") })}</>}
        </Banner>
      ))}
      {s.uncovered.lines > 0 && (
        <Banner tone="warning" title={t("home.coverage.title")}>
          {t("pnl.coverageText", { value: f.number(s.uncovered.lines), amount: f.money(s.uncovered.revenue) })}
        </Banner>
      )}

      <section className="sku__kpis" aria-label={t("products.sku.kpis")}>
        <Kpi label={t("terms.revenue")} value={f.money(sku.revenue)} help={help("revenue", t("terms.revenue"))} />
        <Kpi label={t("terms.netProfit")} value={f.money(sku.net_profit)} help={help("netProfit", t("terms.netProfit"))} note={uncovered} />
        <Kpi label={t("products.col.units")} value={f.number(sku.units)} />
        <Kpi label={t("products.col.avg_price")} value={money(sku.avg_price)} />
        <Kpi label={t("products.col.profit")} value={money(sku.profit_per_unit)} help={help("profitPerUnit", t("products.col.profit"))} />
        {sku.normative_state !== "none" && (
          <Kpi
            label={t("products.col.normative")}
            value={sku.normative_state === "unavailable" ? t("products.normative.unavailable") : money(sku.normative_profit_per_unit)}
            note={sku.normative_state === "adjusted" && sku.saved_per_unit !== null ? t("products.sku.saved", { value: f.money(sku.saved_per_unit) }) : undefined}
            help={help("normative", t("products.col.normative"))}
          />
        )}
        <Kpi label={t("terms.margin")} value={percent(sku.margin)} help={help("margin", t("terms.margin"))} />
        <Kpi label={t("terms.roi")} value={percent(sku.roi)} help={help("roi", t("terms.roi"))} />
        <Kpi label={t("products.col.cogs")} value={money(sku.cogs_per_unit)} help={help("cogs", t("products.col.cogs"))} />
        <Kpi label={t("home.kpis.returns")} value={percent(sku.return_share)} good="down" help={help("returns", t("home.kpis.returns"))} />
        <Kpi label={t("home.kpis.cancel")} value={percent(sku.cancel_share)} good="down" help={help("cancel", t("home.kpis.cancel"))} />
        <Kpi
          label={t("terms.stock")}
          value={f.number(sku.stock)}
          note={sku.days_of_stock === null ? undefined : t("products.sku.days", { value: f.number(sku.days_of_stock, { digits: 0 }) })}
          help={help("stockDays", t("terms.stockDays"))}
        />
      </section>

      <Charts detail={detail} waivers={waivers} />
      <Lots detail={detail} />
      <Returns detail={detail} />
      <LinkItem orgId={orgId} detail={detail} canManage={canManage} />
      <Calculator orgId={orgId} defaults={detail.calc} />
    </>
  );
}

function Charts({ detail, waivers }: { detail: SkuDetail; waivers: SkuDetail["bonus"]["waivers"] }) {
  const { t } = useTranslation();
  const days = detail.history.map((d) => d.day);
  const bands: Band[] = waivers.map((w) => ({ from: w.start_on, to: w.end_on, kind: "shade", label: t("pnl.waivers.badge") }));
  return (
    <section className="sku__charts" aria-label={t("products.sku.history")}>
      <LineBarChart
        title={t("products.sku.chartSales")}
        x={days}
        bands={bands}
        series={[
          { key: "revenue", name: t("terms.revenue"), color: 1, values: detail.history.map((d) => (d.units > 0 ? d.revenue : null)) },
          { key: "profit", name: t("terms.netProfit"), color: "ink", kind: "line", values: detail.history.map((d) => (d.units > 0 ? d.net_profit : null)) },
        ]}
      />
      <LineBarChart
        title={t("products.sku.chartPrice")}
        x={days}
        series={[{ key: "price", name: t("products.sku.price"), color: 2, kind: "line", values: detail.history.map((d) => d.price) }]}
      />
      <LineBarChart
        title={t("products.sku.chartStock")}
        x={days}
        unit="count"
        series={[{ key: "stock", name: t("terms.stock"), color: 3, values: detail.history.map((d) => (d.stock === null ? null : String(d.stock))) }]}
      />
    </section>
  );
}

function Lots({ detail }: { detail: SkuDetail }) {
  const { t } = useTranslation();
  const f = useFormat();
  const columns: Column<SkuLot>[] = [
    { key: "ready", header: t("products.lots.ready"), render: (l) => (l.ready_on ? f.date(l.ready_on) : <Badge tone="info">{t("terms.inTransit")}</Badge>) },
    { key: "qty", header: t("products.lots.qty"), numeric: true, render: (l) => f.number(l.qty) },
    { key: "unit", header: t("products.lots.unitCost"), numeric: true, render: (l) => f.money(l.unit_cost, { unit: false }) },
    { key: "total", header: t("products.lots.total"), numeric: true, render: (l) => f.money(l.total, { unit: false }) },
    { key: "flags", header: t("products.lots.flags"), render: (l) => (l.flags.length === 0 ? "—" : l.flags.map((x) => t(`products.lots.flag.${x}`, { defaultValue: x })).join(", ")) },
  ];
  return (
    <section className="sku__block" aria-labelledby="sku-lots">
      <h2 id="sku-lots" className="h3">
        {t("products.lots.title")}
      </h2>
      {detail.linked === null ? (
        <p className="muted">{t("products.lots.noItem")}</p>
      ) : detail.lots.length === 0 ? (
        <p className="muted">{t("products.lots.empty")}</p>
      ) : (
        <DataTable caption={t("products.lots.title")} columns={columns} rows={detail.lots} rowKey={(l) => l.id} density="compact" />
      )}
    </section>
  );
}

function Returns({ detail }: { detail: SkuDetail }) {
  const { t } = useTranslation();
  const f = useFormat();
  return (
    <section className="sku__block" aria-labelledby="sku-returns">
      <h2 id="sku-returns" className="h3">
        {t("products.returns.title")}
      </h2>
      {detail.returns.length === 0 ? (
        <p className="muted">{t("products.returns.empty")}</p>
      ) : (
        <DataTable
          caption={t("products.returns.title")}
          columns={[
            { key: "cause", header: t("products.returns.cause"), render: (r) => r.cause ?? t("products.returns.noCause") },
            { key: "units", header: t("products.col.units"), numeric: true, render: (r) => f.number(r.units) },
          ]}
          rows={detail.returns}
          rowKey={(r) => r.cause ?? "none"}
          density="compact"
        />
      )}
    </section>
  );
}
