// Xaridlar ro'yxati (M9, B4.6; 04 §7.4): bosqich guruhi (URL'da), har xaridda ixcham Partiya yo'li, dona (buyurtma /
// qabul), jami va o'rtacha tannarx/dona (F20 — jonli, API'dan; taxminiy bo'lsa "~"). "Yangi xarid" — egasi, menejer,
// omborchi (`manage_purchases`); omborchi summalarni ko'rmaydi.
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, purchasesQuery } from "../../app/query";
import { PURCHASE_GROUPS, purchasesSearch, type PurchaseGroup } from "../../app/search";
import { Badge, Banner, Button, DataTable, EmptyState, ExportButton, Skeleton, type Column, PageHelp } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { PurchaseRow, StageMark } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { GROUP_STAGES, isEstimated } from "./model";
import { PurchaseForm } from "./PurchaseForm";

export const MANAGE_ROLES = ["owner", "manager", "warehouse"];

/** Ixcham Partiya yo'li: nuqtalar qatori + joriy bosqich nomi, kunlari va kutilgan sana. */
export function CompactPath({ marks }: { marks: StageMark[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const current = marks.find((m) => m.state === "current");
  const closed = marks.every((m) => m.state === "done");
  const label = current ? t(`purchases.stage.${current.stage}`) : closed ? t("purchases.stage.closed") : t("purchases.stage.draft");
  return (
    <span className="purchase-path">
      <span className="purchase-path__dots" aria-hidden>
        {marks.map((m) => (
          <span key={m.stage} className={cx("purchase-path__dot", `is-${m.state}`, m.delayed && "is-delayed")} />
        ))}
      </span>
      <span className="purchase-path__label">
        {label}
        {current?.days != null && <span className="caption"> · {t("ui.daysPassed", { count: current.days })}</span>}
        {current?.expected && <span className="caption"> · {t("ui.expected", { date: f.date(current.expected).slice(0, 5) })}</span>}
        {current?.delayed && (
          <span className="ui-text--warning caption">
            {" "}
            <TriangleAlert size={14} aria-hidden /> {t("ui.status.delayed")}
          </span>
        )}
      </span>
    </span>
  );
}

export function Purchases() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const navigate = useNavigate();
  const group = purchasesSearch(useSearch({ strict: false }) as Record<string, unknown>).group;
  const query = useQuery(purchasesQuery(org.id, group ? GROUP_STAGES[group] : []));
  const [adding, setAdding] = useState(false);
  const canManage = MANAGE_ROLES.includes(org.role);
  const amounts = query.data?.amounts ?? true;
  const setGroup = (next: PurchaseGroup | undefined) => void navigate({ to: "/purchases", search: (prev) => ({ ...prev, group: next }), replace: true });
  const units = (r: PurchaseRow) =>
    r.units_received === null ? t("purchases.unitsOrdered", { ordered: f.number(r.units_ordered) }) : t("purchases.unitsReceived", { received: f.number(r.units_received), ordered: f.number(r.units_ordered) });
  const columns: Column<PurchaseRow>[] = [
    {
      key: "purchase",
      header: t("purchases.col.purchase"),
      render: (r) => (
        <span className="purchase-cell">
          <Link to="/purchases/$purchaseId" params={{ purchaseId: r.id }} className="purchase-cell__title">
            {r.title ?? t("purchases.untitled")}
          </Link>
          {r.items.length > 0 && (
            <span className="caption">
              {r.items.join(", ")}
              {r.line_count > r.items.length && ` ${t("purchases.more", { count: r.line_count - r.items.length })}`}
            </span>
          )}
        </span>
      ),
    },
    { key: "supplier", header: t("purchases.col.supplier"), render: (r) => r.supplier_name ?? "—" },
    { key: "path", header: t("purchases.col.path"), render: (r) => <CompactPath marks={r.timeline} /> },
    { key: "units", header: t("purchases.col.units"), numeric: true, render: units },
    ...(amounts
      ? [
          { key: "total", header: t("purchases.col.total"), numeric: true, render: (r: PurchaseRow) => (r.total === null ? "—" : f.money(r.total, { unit: false })) },
          {
            key: "unit",
            header: t("purchases.col.unitCost"),
            numeric: true,
            render: (r: PurchaseRow) =>
              r.error ? (
                <Badge tone="negative">{t("purchases.notCalculated")}</Badge>
              ) : r.unit_cost === null ? (
                "—"
              ) : (
                <span title={isEstimated(r.flags) ? t("terms.estimated") : undefined}>
                  {isEstimated(r.flags) && "~"}
                  {f.money(r.unit_cost, { unit: false })}
                </span>
              ),
          },
        ]
      : []),
  ];
  return (
    <section className="purchases">
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("purchases.title")}</h1>
          <PageHelp page="purchases" />
        </div>
        <span className="purchases__actions">
          <ExportButton orgId={org.id} table="purchases" />
          {canManage && <Button onClick={() => setAdding(true)}>{t("purchases.add")}</Button>}
        </span>
      </header>
      <div role="tablist" aria-label={t("purchases.groupsLabel")} className="orders-tabs">
        {([undefined, ...PURCHASE_GROUPS] as const).map((id) => (
          <button
            key={id ?? "all"}
            type="button"
            role="tab"
            aria-selected={group === id}
            aria-controls="purchases-panel"
            className={cx("orders-tab", group === id && "is-active")}
            onClick={() => setGroup(id)}
          >
            {t(`purchases.groups.${id ?? "all"}`)}
          </button>
        ))}
      </div>
      <div id="purchases-panel" role="tabpanel" aria-label={t("purchases.list")} className="purchases__panel">
        {!amounts && <Banner tone="info" title={t("purchases.noAmounts")}>{t("purchases.noAmountsText")}</Banner>}
        {query.isError ? (
          <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
        ) : !query.data ? (
          <Skeleton label={t("common.loading")} lines={6} />
        ) : query.data.items.length === 0 ? (
          group ? (
            <EmptyState title={t("purchases.emptyGroup")} />
          ) : (
            <EmptyState title={t("purchases.empty")} text={t("purchases.emptyText")} action={canManage ? <Button onClick={() => setAdding(true)}>{t("purchases.add")}</Button> : undefined} />
          )
        ) : (
          <DataTable caption={t("purchases.list")} columns={columns} rows={query.data.items} rowKey={(r) => r.id} />
        )}
      </div>
      {adding && (
        <PurchaseForm
          orgId={org.id}
          detail={null}
          onClose={() => setAdding(false)}
          onSaved={(saved) => void navigate({ to: "/purchases/$purchaseId", params: { purchaseId: saved.purchase.id } })}
        />
      )}
    </section>
  );
}
