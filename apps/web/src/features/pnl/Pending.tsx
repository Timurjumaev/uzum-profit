// Kutilayotgan (M5, F16): Jarayondagi sotuvlardan kutilayotgan foyda alohida blok — realizatsiya darajasi bilan;
// do'konlar bo'yicha (R har do'konda alohida). R hisoblanmasa (ma'lumot kam) — koeffitsientsiz summa va sababi.
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
  const amount = (x: { amount: string | null }) => (x.amount === null ? "—" : f.money(x.amount));
  const rate = (x: { rate: string | null; raw: string }) =>
    x.rate === null ? t("pnl.pending.noRate", { raw: f.money(x.raw) }) : t("pnl.pending.rate", { rate: f.percent(x.rate) });
  const shopName = (id: string) => {
    const shop = shops.data?.find((s) => s.id === id);
    return shop ? (shop.alias ?? shop.name) : id.slice(0, 8);
  };
  const columns: Column<ShopPending>[] = [
    { key: "shop", header: t("pnl.pending.shop"), render: (r) => shopName(r.shop_id) },
    { key: "amount", header: t("pnl.pending.amount"), numeric: true, render: (r) => amount(r) },
    { key: "rate", header: t("pnl.pending.rateHeader"), render: (r) => (r.rate === null ? t("pnl.pending.raw", { raw: f.money(r.raw) }) : f.percent(r.rate)) },
  ];
  return (
    <section aria-labelledby="pnl-pending" className="pnl-pending">
      <h2 id="pnl-pending" className="h3">
        {t("pnl.pending.title")}{" "}
        <FormulaPopover
          metric={t("terms.expectedProfit")}
          code={t("home.formula.expected.code")}
          formula={t("home.formula.expected.formula")}
          source={t("home.formula.expected.source")}
          estimatedReason={t("home.formula.expected.estimated")}
        />
      </h2>
      {data.pending_shops.length === 0 ? (
        <p className="muted">{t("pnl.pending.empty")}</p>
      ) : (
        <>
          <p className="kpi num" data-testid="pending-amount">
            {amount(p)}
          </p>
          <p className="caption">{rate(p)}</p>
          {p.uncovered_lines > 0 && <p className="caption">{t("pnl.pending.uncovered", { value: f.number(p.uncovered_lines) })}</p>}
          {data.pending_shops.length > 1 && (
            <DataTable caption={t("pnl.pending.title")} density="compact" columns={columns} rows={data.pending_shops} rowKey={(r) => r.shop_id} />
          )}
        </>
      )}
    </section>
  );
}
