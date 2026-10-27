// Sotuv qatorlari ro'yxati (M7): sana, holat, SKU, dona, narx, komissiya, logistika, Uzum to'lovi, tannarx, foyda.
// Uzum bonusi davridagi buyurtma — "Bonus davri" belgisi (ADR-031); tannarxsiz yoki taxminiy qator belgilanadi
// (tamoyil 9). Yuqorida davr bo'yicha bekor (F17) va qaytish (F18) ulushi — holat filtriga bog'liq emas.
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { ordersQuery, type ReportParams } from "../../app/query";
import { ORDER_GROUPS, ordersSearch, type OrderGroup } from "../../app/search";
import { Badge, Banner, Button, DataTable, EmptyState, FormulaPopover, Select, Skeleton, type Column, type Tone } from "../../components/ui";
import type { Sale } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

const GROUP_TONE: Record<Sale["group"], Tone> = { completed: "positive", processing: "info", canceled: "negative", unknown: "warning" };

type Props = { orgId: string; params: ReportParams; group: OrderGroup | undefined };

export function OrdersList({ orgId, params, group }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const navigate = useNavigate();
  const query = useInfiniteQuery({ ...ordersQuery(orgId, params, group), placeholderData: keepPreviousData });
  if (query.isError && !query.data) {
    return <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />;
  }
  if (!query.data) return <Skeleton label={t("common.loading")} lines={8} />;

  const first = query.data.pages[0]!;
  const rows = query.data.pages.flatMap((p) => p.items);
  const share = (value: string | null) => (value === null ? "—" : f.percent(value));
  const columns: Column<Sale>[] = [
    { key: "day", header: t("orders.col.day"), render: (r) => f.date(r.day) },
    {
      key: "status",
      header: t("orders.col.status"),
      render: (r) => <Badge tone={GROUP_TONE[r.group]}>{t(`orders.group.${r.group}`)}</Badge>,
    },
    {
      key: "sku",
      header: t("orders.col.sku"),
      render: (r) => (
        <>
          {r.sku_title ?? t("orders.unlinked")}
          {r.waiver_id && (
            <>
              {" "}
              <span title={t("pnl.waivers.badgeTitle")}>
                <Badge tone="info">{t("pnl.waivers.badge")}</Badge>
              </span>
            </>
          )}
        </>
      ),
    },
    { key: "amount", header: t("orders.col.units"), numeric: true, render: (r) => f.number(r.amount) },
    { key: "price", header: t("orders.col.price"), numeric: true, render: (r) => f.money(r.sell_price, { unit: false }) },
    { key: "commission", header: t("terms.commission"), numeric: true, render: (r) => f.money(r.commission, { unit: false }) },
    { key: "logistics", header: t("terms.logistics"), numeric: true, render: (r) => f.money(r.logistics, { unit: false }) },
    { key: "payout", header: t("terms.payout"), numeric: true, render: (r) => f.money(r.payout, { unit: false }) },
    {
      key: "cogs",
      header: t("terms.cogs"),
      numeric: true,
      render: (r) => (
        <>
          {r.cost_flags.length > 0 && <Badge tone="warning">{t("orders.estimated")}</Badge>} {r.cogs === null ? "—" : f.money(r.cogs, { unit: false })}
        </>
      ),
    },
    { key: "profit", header: t("terms.grossProfit"), numeric: true, render: (r) => (r.gross_profit === null ? "—" : f.money(r.gross_profit, { unit: false })) },
  ];
  const s = first.summary;
  return (
    <div className="orders-list" aria-busy={query.isPlaceholderData || undefined}>
      <p className="orders-summary caption">
        {t("orders.summary", { units: f.number(s.units), canceled: f.number(s.canceled), returns: f.number(s.returns) })}{" "}
        <span>
          {t("orders.cancelShare")}: <b className="num">{share(s.cancel_share)}</b>
          <FormulaPopover metric={t("orders.cancelShare")} code={t("home.formula.cancel.code")} formula={t("home.formula.cancel.formula")} source={t("home.formula.cancel.source")} />
        </span>{" "}
        <span>
          {t("orders.returnShare")}: <b className="num">{share(s.return_share)}</b>
          <FormulaPopover metric={t("orders.returnShare")} code={t("home.formula.returns.code")} formula={t("home.formula.returns.formula")} source={t("home.formula.returns.source")} />
        </span>
      </p>
      <div className="orders-filters">
        <Select
          label={t("orders.col.status")}
          value={group ?? ""}
          onValueChange={(v) => void navigate({ to: "/orders", search: (prev) => ({ ...prev, group: ordersSearch({ group: v }).group }), replace: true })}
          options={[{ value: "", label: t("orders.group.all") }, ...ORDER_GROUPS.map((g) => ({ value: g, label: t(`orders.group.${g}`) }))]}
        />
      </div>
      {rows.length === 0 ? (
        <EmptyState title={t("orders.empty")} text={t("orders.emptyText")} />
      ) : (
        <>
          <DataTable caption={t("orders.caption")} density="compact" columns={columns} rows={rows} rowKey={(r) => r.id} />
          {query.hasNextPage && (
            <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              {t("orders.loadMore")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}
