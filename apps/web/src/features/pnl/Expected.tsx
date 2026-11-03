// Kutilayotgan sof foyda (M5, F16, ADR-037): Jarayondagi sotuvlar — mijoz hali olmagan yoki qaytarish muddati (10 kun)
// tugamagan. Ular xuddi yakunlanganlar kabi hisoblangan (hisob varag'ining "Kutilayotgan" ustuni); bu blok nima uchun hali aniq
// emasligini ko'rsatadi: dona va tushum, yakunlanish darajasi — fakt (oxirgi 90 kunda shunday sotuvlarning necha foizi
// yakunlangan, summaga ko'paytirilmaydi), taxminiy logistika va reklama (F42) va tannarxsiz qism. Do'konlar bo'yicha jadval.
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { shopsQuery } from "../../app/query";
import { DataTable, FormulaPopover, type Column } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { Pnl } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { term } from "../../lib/i18n/glossary";

type ShopExpected = Pnl["expected_shops"][number];

export function Expected({ orgId, data }: { orgId: string; data: Pnl }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shops = useQuery(shopsQuery(orgId));
  const e = data.expected;
  const title = t(term("netExpected"));
  const shopName = (id: string) => {
    const shop = shops.data?.find((s) => s.id === id);
    return shop ? (shop.alias ?? shop.name) : id.slice(0, 8);
  };
  const columns: Column<ShopExpected>[] = [
    { key: "shop", header: t("pnl.expected.shop"), render: (r) => shopName(r.shop_id) },
    { key: "units", header: t("pnl.expected.units"), numeric: true, render: (r) => f.number(r.units) },
    { key: "revenue", header: t("pnl.expected.revenue"), numeric: true, render: (r) => f.money(r.revenue, { unit: false }) },
    { key: "profit", header: t("pnl.col.processing"), numeric: true, render: (r) => f.money(r.net_profit, { unit: false }) },
    { key: "rate", header: t("pnl.expected.rateHeader"), numeric: true, render: (r) => (r.rate === null ? "—" : f.percent(r.rate)) },
  ];
  return (
    <section aria-labelledby="pnl-expected" className="pnl-pending">
      <h2 id="pnl-expected" className="h3">
        {title}{" "}
        <FormulaPopover
          metric={title}
          code={t("home.formula.netExpected.code")}
          formula={t("home.formula.netExpected.formula")}
          source={t("home.formula.netExpected.source")}
          estimatedReason={t("home.formula.netExpected.estimated")}
        />
      </h2>
      {e.units === 0 ? (
        <p className="muted">{t("pnl.expected.empty")}</p>
      ) : (
        <>
          <p className={cx("kpi num", Number(e.net_profit) < 0 ? "ui-text--negative" : "ui-text--positive")} data-testid="expected-amount">
            {f.money(e.net_profit)}
          </p>
          <p className="caption">{t("pnl.expected.summary", { units: f.number(e.units), revenue: f.money(e.revenue) })}</p>
          <p className="caption">{e.rate === null ? t("pnl.expected.noRate") : t("pnl.expected.rate", { rate: f.percent(e.rate) })}</p>
          {e.logistics_estimated_units > 0 && (
            <p className="caption">
              {t("pnl.expected.logistics", { units: f.number(e.logistics_estimated_units), amount: f.money(e.logistics_estimated) })}
            </p>
          )}
          {Number(e.uzum_estimated.advertising ?? 0) !== 0 && (
            <p className="caption">{t("pnl.expected.ads", { amount: f.money(e.uzum_estimated.advertising!) })}</p>
          )}
          {e.uncovered_lines > 0 && <p className="caption">{t("pnl.expected.uncovered", { value: f.number(e.uncovered_lines) })}</p>}
          {data.expected_shops.length > 1 && (
            <DataTable caption={title} density="compact" columns={columns} rows={data.expected_shops} rowKey={(r) => r.shop_id} />
          )}
        </>
      )}
    </section>
  );
}
