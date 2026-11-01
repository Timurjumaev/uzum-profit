// Bosh sahifa bloklari (M4): davr chizig'i, kunlik grafik, "Diqqat talab qiladi", TOP/zarar SKU, ko'rsatkichlar.
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, FormulaPopover, Kpi, StatusPill, type Column } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { LineBarChart } from "../../components/charts";
import type { Dashboard } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import type { AttentionItem } from "./model";

const tone = (value: string) => (Number(value) < 0 ? "negative" : "positive");

// --- Davr chizig'i -------------------------------------------------------------------------------------------------

export function PeriodStrip({ data }: { data: Dashboard }) {
  const { t } = useTranslation();
  const f = useFormat();
  const byKey = new Map(data.periods.map((p) => [p.key, p]));
  const forecast = data.forecast;
  const tiles = [
    { key: "today", label: t("home.periods.today"), p: byKey.get("today") },
    { key: "yesterday", label: t("home.periods.yesterday"), p: byKey.get("yesterday") },
    { key: "this_month", label: t("home.periods.this_month"), p: byKey.get("this_month") },
    { key: "forecast", label: t("home.periods.forecast"), forecast },
    { key: "last_month", label: t("home.periods.last_month"), p: byKey.get("last_month") },
  ];
  return (
    <section aria-labelledby="home-periods" className="home-periods">
      <h2 id="home-periods" className="ui-visually-hidden">
        {t("home.periods.title")}
      </h2>
      <ul>
        {tiles.map((tile) => {
          const revenue = tile.p?.revenue ?? tile.forecast?.revenue ?? null;
          const net = tile.p?.net_profit ?? tile.forecast?.net_profit ?? null;
          const units = tile.p ? String(tile.p.units) : (tile.forecast?.units ?? null);
          return (
            <li key={tile.key} className="home-period">
              <h3 className="label">
                {tile.label}
                {tile.forecast && (
                  <>
                    {" "}
                    <FormulaPopover
                      metric={tile.label}
                      code="M4"
                      formula={t("home.periods.forecastFormula")}
                      source={t("home.periods.forecastSource")}
                      estimatedReason={t("home.periods.forecastEstimated")}
                    />
                  </>
                )}
              </h3>
              {revenue === null ? (
                <p className="caption">{t("home.periods.noForecast")}</p>
              ) : (
                <dl>
                  <div>
                    <dt className="caption">{t("home.periods.revenue")}</dt>
                    <dd className="num">{f.money(revenue)}</dd>
                  </div>
                  <div>
                    <dt className="caption">{t("home.periods.netProfit")}</dt>
                    <dd className={cx("num", `ui-text--${tone(net ?? "0")}`)}>{net === null ? "—" : f.money(net)}</dd>
                  </div>
                  <div>
                    <dt className="caption">{t("home.periods.units")}</dt>
                    <dd className="num">{units === null ? "—" : t("home.periods.unitsValue", { value: f.number(units, { digits: 0 }) })}</dd>
                  </div>
                </dl>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// --- Kunlik grafik -------------------------------------------------------------------------------------------------

export function DailyChart({ data }: { data: Dashboard }) {
  const { t } = useTranslation();
  return (
    <LineBarChart
      title={t("home.chart.title")}
      x={data.daily.map((d) => d.day)}
      series={[
        { key: "revenue", name: t("home.chart.revenue"), color: 1, values: data.daily.map((d) => d.revenue) },
        { key: "net", name: t("home.chart.netProfit"), color: "ink", kind: "line", values: data.daily.map((d) => d.net_profit) },
      ]}
    />
  );
}

// --- Diqqat talab qiladi -------------------------------------------------------------------------------------------

export function Attention({ items }: { items: AttentionItem[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  return (
    <section aria-labelledby="home-attention" className="home-attention">
      <h2 id="home-attention" className="h3">
        {t("home.attention.title")}
      </h2>
      {items.length === 0 ? (
        <p className="muted">
          <strong>{t("home.attention.empty")}.</strong> {t("home.attention.emptyText")}
        </p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.kind}>
              <StatusPill tone={item.tone}>
                {t(`home.attention.${item.kind}`, { value: f.number(item.count), amount: item.amount ? f.money(item.amount) : "" })}
              </StatusPill>
              <Link to={item.to} search={(prev) => prev} className="home-attention__link">
                {t("home.attention.view")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- Eng foydali 5 / zarar 5 ---------------------------------------------------------------------------------------

type Brief = Dashboard["top"][number];

function SkuTable({ title, rows, empty }: { title: string; rows: Brief[]; empty: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const columns: Column<Brief>[] = [
    { key: "name", header: t("home.sku.name"), render: (r) => r.title ?? r.product_title ?? t("home.sku.unnamed") },
    { key: "units", header: t("home.sku.units"), numeric: true, render: (r) => f.number(r.units) },
    {
      key: "profit",
      header: t("home.sku.profit"),
      numeric: true,
      render: (r) => <span className={`ui-text--${tone(r.net_profit)}`}>{f.money(r.net_profit, { unit: false })}</span>,
    },
  ];
  return <DataTable caption={title} density="compact" columns={columns} rows={rows} rowKey={(r) => r.sku_id} empty={empty} />;
}

export function SkuLists({ top, bottom }: { top: Brief[]; bottom: Brief[] }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"top" | "bottom">("top");
  const tabs = [
    { key: "top" as const, label: t("home.sku.top") },
    { key: "bottom" as const, label: t("home.sku.bottom") },
  ];
  return (
    <div className="home-skus" data-tab={tab}>
      <div role="tablist" aria-label={t("home.sku.top") + " / " + t("home.sku.bottom")} className="home-skus__tabs">
        {tabs.map((x) => (
          <button
            key={x.key}
            type="button"
            role="tab"
            id={`home-sku-tab-${x.key}`}
            aria-selected={tab === x.key}
            aria-controls={`home-sku-${x.key}`}
            className={cx("home-skus__tab", tab === x.key && "is-active")}
            onClick={() => setTab(x.key)}
          >
            {x.label}
          </button>
        ))}
      </div>
      <section id="home-sku-top" role="tabpanel" aria-labelledby="home-sku-tab-top" className="home-skus__panel" data-panel="top">
        <h2 className="h3 home-skus__title">{t("home.sku.top")}</h2>
        <SkuTable title={t("home.sku.top")} rows={top} empty={t("home.sku.topEmpty")} />
      </section>
      <section id="home-sku-bottom" role="tabpanel" aria-labelledby="home-sku-tab-bottom" className="home-skus__panel" data-panel="bottom">
        <h2 className="h3 home-skus__title">{t("home.sku.bottom")}</h2>
        <SkuTable title={t("home.sku.bottom")} rows={bottom} empty={t("home.sku.bottomEmpty")} />
      </section>
    </div>
  );
}

// --- Qo'shimcha ko'rsatkichlar -------------------------------------------------------------------------------------

export function Kpis({ data }: { data: Dashboard }) {
  const { t } = useTranslation();
  const f = useFormat();
  const k = data.kpis;
  const percent = (v: string | null) => (v === null ? "—" : f.percent(v));
  const help = (key: string, metric: string) => (
    <FormulaPopover
      metric={metric}
      code={t(`home.formula.${key}.code`)}
      formula={t(`home.formula.${key}.formula`)}
      source={t(`home.formula.${key}.source`)}
      estimatedReason={key === "expected" ? t("home.formula.expected.estimated") : undefined}
    />
  );
  const uncovered = Number(k.uncovered_share) > 0 ? t("home.kpis.uncovered", { share: f.percent(k.uncovered_share) }) : undefined;
  const expected = k.expected_profit;
  return (
    <section aria-labelledby="home-kpis" className="home-kpis">
      <h2 id="home-kpis" className="h3">
        {t("home.kpis.title")}
      </h2>
      <div className="home-kpis__grid">
        <Kpi label={t("home.kpis.margin")} value={percent(k.margin)} note={k.margin === null ? t("home.kpis.noCostedSales") : uncovered} help={help("margin", t("home.kpis.margin"))} />
        <Kpi label={t("home.kpis.roi")} value={percent(k.roi)} help={help("roi", t("home.kpis.roi"))} />
        <Kpi label={t("home.kpis.cancel")} value={percent(k.cancel_share)} good="down" help={help("cancel", t("home.kpis.cancel"))} />
        <Kpi label={t("home.kpis.returns")} value={percent(k.return_share)} good="down" help={help("returns", t("home.kpis.returns"))} />
        <Kpi label={t("home.kpis.drr")} value={percent(k.drr)} good="down" help={help("drr", t("home.kpis.drr"))} />
        <Kpi
          label={t("home.kpis.frozen")}
          value={f.money(k.frozen_money)}
          note={k.average_days_to_sell === null ? undefined : t("home.kpis.frozenNote", { days: f.number(k.average_days_to_sell, { digits: 0 }) })}
          help={help("frozen", t("home.kpis.frozen"))}
        />
        <Kpi label={t("home.kpis.inTransit")} value={f.money(k.in_transit_value)} help={help("inTransit", t("home.kpis.inTransit"))} />
        <Kpi
          label={t("home.kpis.expected")}
          value={expected.amount === null ? "—" : f.money(expected.amount)}
          note={expected.rate === null ? t("home.kpis.expectedNoRate", { raw: f.money(expected.raw) }) : t("home.kpis.expectedRate", { rate: f.percent(expected.rate) })}
          help={help("expected", t("home.kpis.expected"))}
        />
      </div>
    </section>
  );
}
