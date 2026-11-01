// Jarayondagi sotuvlar (M5, F16, ADR-036): ular tushum va foydaga allaqachon kirgan — bu blok qaysi qismi hali
// yakuniy emasligini ko'rsatadi: dona, tushum, yalpi foyda (tannarxi ma'lum qism). Realizatsiya darajasi — fakt
// (oxirgi 90 kunda shunday sotuvlarning necha foizi yakunlangan), summaga ko'paytirilmaydi. Do'konlar bo'yicha jadval.
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { shopsQuery } from "../../app/query";
import { DataTable, FormulaPopover, type Column } from "../../components/ui";
import type { Pnl } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type ShopPending = Pnl["pending_shops"][number];

export function Pending({ orgId, data }: { orgId: string; data: Pnl }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shops = useQuery(shopsQuery(orgId));
  const p = data.pending;
  const shopName = (id: string) => {
    const shop = shops.data?.find((s) => s.id === id);
    return shop ? (shop.alias ?? shop.name) : id.slice(0, 8);
  };
  const columns: Column<ShopPending>[] = [
    { key: "shop", header: t("pnl.pending.shop"), render: (r) => shopName(r.shop_id) },
    { key: "units", header: t("pnl.pending.units"), numeric: true, render: (r) => f.number(r.units) },
    { key: "revenue", header: t("pnl.pending.revenue"), numeric: true, render: (r) => f.money(r.revenue, { unit: false }) },
    { key: "profit", header: t("pnl.pending.profit"), numeric: true, render: (r) => f.money(r.profit, { unit: false }) },
    { key: "rate", header: t("pnl.pending.rateHeader"), numeric: true, render: (r) => (r.rate === null ? "—" : f.percent(r.rate)) },
  ];
  return (
    <section aria-labelledby="pnl-pending" className="pnl-pending">
      <h2 id="pnl-pending" className="h3">
        {t("pnl.pending.title")}{" "}
        <FormulaPopover
          metric={t("pnl.pending.title")}
          code={t("home.formula.processing.code")}
          formula={t("home.formula.processing.formula")}
          source={t("home.formula.processing.source")}
          estimatedReason={t("home.formula.processing.estimated")}
        />
      </h2>
      {data.pending_shops.length === 0 ? (
        <p className="muted">{t("pnl.pending.empty")}</p>
      ) : (
        <>
          <p className="kpi num" data-testid="pending-amount">
            {f.money(p.revenue)}
          </p>
          <p className="caption">{t("pnl.pending.summary", { units: f.number(p.units), profit: f.money(p.profit) })}</p>
          <p className="caption">{p.rate === null ? t("pnl.pending.noRate") : t("pnl.pending.rate", { rate: f.percent(p.rate) })}</p>
          {p.uncovered_lines > 0 && <p className="caption">{t("pnl.pending.uncovered", { value: f.number(p.uncovered_lines) })}</p>}
          {data.pending_shops.length > 1 && (
            <DataTable caption={t("pnl.pending.title")} density="compact" columns={columns} rows={data.pending_shops} rowKey={(r) => r.shop_id} />
          )}
        </>
      )}
    </section>
  );
}
