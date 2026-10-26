// Kesimlar (M5): oylar va do'konlar — qator = P&L qatori, ustun = oy / do'kon + jami (04 §7.4: "ustun = oy");
// SKU — qator = SKU (ko'p bo'ladi), ustun = asosiy qatorlar. Do'kon va SKU kesimida Uzum va o'z xarajatlari
// to'g'ridan-to'g'ri va taqsimlangan qismlarga bo'linadi, sotuvsiz kun xarajati — "Taqsimlanmagan" (ADR-026).
// Ustunlar yig'indisi = jami — API kafolati (kataklar yig'indisi); bu yerda hech narsa qo'shilmaydi.
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { shopsQuery } from "../../app/query";
import { Button, Skeleton } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { Pnl, Statement } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { negate } from "../home/model";
import { breakdownLines, skuOrder, VIEWS, type Column, type View } from "./model";

const PAGE = 50;

type Props = { orgId: string; data: Pnl; view: View; busy: boolean };

export function Breakdown({ orgId, data, view, busy }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setView = (next: View) =>
    void navigate({ to: "/pnl", search: (prev) => ({ ...prev, view: next === "month" ? undefined : next }), replace: true });
  return (
    <section aria-labelledby="pnl-views" className="pnl-views" aria-busy={busy || undefined}>
      <h2 id="pnl-views" className="h3">
        {t("pnl.views.title")}
      </h2>
      <div role="tablist" aria-label={t("pnl.views.title")} className="pnl-tabs">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            id={`pnl-tab-${v}`}
            aria-selected={view === v}
            aria-controls="pnl-view-panel"
            className={cx("pnl-tab", view === v && "is-active")}
            onClick={() => setView(v)}
          >
            {t(`pnl.views.${v}`)}
          </button>
        ))}
      </div>
      <div id="pnl-view-panel" role="tabpanel" aria-labelledby={`pnl-tab-${view}`}>
        {view !== "month" && <p className="caption">{t("pnl.views.splitNote")}</p>}
        {busy ? (
          <Skeleton label={t("common.loading")} lines={6} />
        ) : data.columns.length === 0 ? (
          <p className="muted">{t("pnl.views.empty")}</p>
        ) : view === "sku" ? (
          <SkuTable data={data} />
        ) : (
          <LinesTable orgId={orgId} data={data} view={view} />
        )}
      </div>
    </section>
  );
}

function useCell() {
  const f = useFormat();
  return (value: string | null, ratio = false) => (value === null ? "—" : ratio ? f.percent(value) : f.money(value, { unit: false }));
}

function LinesTable({ orgId, data, view }: { orgId: string; data: Pnl; view: "month" | "shop" }) {
  const { t } = useTranslation();
  const f = useFormat();
  const cell = useCell();
  const shops = useQuery({ ...shopsQuery(orgId), enabled: view === "shop" });
  const lines = useMemo(() => breakdownLines(t, view === "shop"), [t, view]);
  const header = (c: Column) => {
    if (c.key === null) return t("pnl.views.unallocated");
    if (view === "month") return f.month(c.key);
    const shop = shops.data?.find((s) => s.id === c.key);
    return shop ? (shop.alias ?? shop.name) : c.key.slice(0, 8);
  };
  const caption = t(`pnl.views.${view}`);
  return (
    <div className="ui-table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table className="ui-table ui-table--compact pnl-lines">
        <caption className="ui-visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{t("pnl.col.line")}</th>
            {data.columns.map((c) => (
              <th key={c.key ?? "null"} scope="col" className="num">
                {header(c)}
              </th>
            ))}
            <th scope="col" className="num">
              {t("pnl.views.total")}
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.key} className={cx(`is-${line.kind}`)}>
              <th scope="row">
                <span className="pnl-op" aria-hidden>
                  {line.op}
                </span>{" "}
                {line.label}
              </th>
              {data.columns.map((c) => (
                <td key={c.key ?? "null"} className="num">
                  {cell(line.value(c.statement), line.ratio)}
                </td>
              ))}
              <td className="num pnl-total">{cell(line.value(data.statement), line.ratio)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type SkuCol = { key: string; header: string; value: (s: Statement) => string | null; ratio?: boolean };

function SkuTable({ data }: { data: Pnl }) {
  const { t } = useTranslation();
  const f = useFormat();
  const cell = useCell();
  const [shown, setShown] = useState(PAGE);
  const rows = useMemo(() => skuOrder(data.columns), [data.columns]);
  const minus = (pick: (s: Statement) => string) => (s: Statement) => negate(pick(s));
  const split = (base: string, kind: "direct" | "allocated") => `${t(base)} — ${t(`pnl.views.${kind}`)}`;
  const cols: SkuCol[] = [
    { key: "revenue", header: t("terms.revenue"), value: (s) => s.revenue },
    { key: "payout", header: t("terms.payout"), value: (s) => s.payout },
    { key: "cogs", header: t("terms.cogs"), value: minus((s) => s.cogs) },
    { key: "uzum_direct", header: split("terms.uzumExpenses", "direct"), value: minus((s) => s.uzum_direct) },
    { key: "uzum_allocated", header: split("terms.uzumExpenses", "allocated"), value: minus((s) => s.uzum_allocated_total) },
    { key: "own_direct", header: split("terms.ownExpenses", "direct"), value: minus((s) => s.own_direct) },
    { key: "own_allocated", header: split("terms.ownExpenses", "allocated"), value: minus((s) => s.own_allocated_total) },
    { key: "tax", header: t("terms.tax"), value: minus((s) => s.tax) },
    { key: "net", header: t("terms.netProfit"), value: (s) => s.net_profit },
    { key: "margin", header: t("pnl.views.margin"), value: (s) => s.margin, ratio: true },
  ];
  const name = (c: Column) => (c.key === null ? t("pnl.views.unallocated") : c.key === "unlinked" ? t("pnl.views.unlinked") : (c.title ?? t("home.sku.unnamed")));
  const caption = t("pnl.views.sku");
  return (
    <>
      <div className="ui-table-wrap" tabIndex={0} role="region" aria-label={caption}>
        <table className="ui-table ui-table--compact pnl-skus">
          <caption className="ui-visually-hidden">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">{t("home.sku.name")}</th>
              {cols.map((c) => (
                <th key={c.key} scope="col" className="num">
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, shown).map((r) => (
              <tr key={r.key ?? "null"}>
                <th scope="row">{name(r)}</th>
                {cols.map((c) => (
                  <td key={c.key} className={cx("num", c.key === "net" && Number(r.statement.net_profit) < 0 && "ui-text--negative")}>
                    {cell(c.value(r.statement), c.ratio)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">{t("pnl.views.total")}</th>
              {cols.map((c) => (
                <td key={c.key} className="num">
                  {cell(c.value(data.statement), c.ratio)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="caption">{t("pnl.views.skuShown", { shown: f.number(Math.min(shown, rows.length)), total: f.number(rows.length) })}</p>
      {shown < rows.length && (
        <Button variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
          {t("pnl.views.more")}
        </Button>
      )}
    </>
  );
}
