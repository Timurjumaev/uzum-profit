// Kargolar ro'yxati (M9, ADR-046; TM3 da soddalashdi — sanalar ustuni yo'q, sahifalash B5.0d): bitta kargo — ko'p xarid.
// Har qatorda xaridlar soni, dona va kargo xarajatlari jami (summalar ruxsati bilan). "Yangi kargo" — egasi, menejer, omborchi (`manage_purchases`).
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, shipmentsPageQuery } from "../../app/query";
import { Banner, Button, DataTable, EmptyState, Pagination, Skeleton, usePageSize, type Column } from "../../components/ui";
import type { Shipment } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { MANAGE_ROLES } from "../purchases/Purchases";
import { ShipmentForm } from "./ShipmentForm";
import { shipmentStatus } from "./ShipmentLink";

export function Shipments() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const navigate = useNavigate();
  const [size, setSize] = usePageSize();
  const [page, setPage] = useState(1);
  const query = useQuery({ ...shipmentsPageQuery(org.id, page, size), placeholderData: keepPreviousData });
  const [adding, setAdding] = useState(false);
  const canManage = MANAGE_ROLES.includes(org.role);
  const amounts = query.data?.amounts ?? true;
  /** Mobil meta qator uchun holat: eng oxirgi to'ldirilgan bosqich va sanasi. */
  const status = (r: Shipment) => {
    const st = shipmentStatus(r);
    return st ? `${t(`purchases.stage.${st.stage}`)} ${f.date(st.on)}` : null;
  };
  const columns: Column<Shipment>[] = [
    {
      key: "shipment",
      header: t("shipments.col.shipment"),
      render: (r) => (
        <span className="purchase-cell">
          <Link to="/shipments/$shipmentId" params={{ shipmentId: r.id }} className="purchase-cell__title">
            {r.title || t("shipments.untitled")}
          </Link>
          {r.note && <span className="caption">{r.note}</span>}
          <span className="caption purchase-cell__meta">
            {[r.carrier_name, status(r), t("shipments.units", { count: r.units })].filter(Boolean).join(" · ")}
          </span>
        </span>
      ),
    },
    { key: "carrier", header: t("purchases.fields.carrier"), render: (r) => r.carrier_name ?? "—" },
    { key: "purchases", header: t("shipments.col.purchases"), numeric: true, render: (r) => f.number(r.purchase_count) },
    { key: "units", header: t("purchases.col.units"), numeric: true, render: (r) => f.number(r.units) },
    ...(amounts ? [{ key: "total", header: t("shipments.col.total"), numeric: true, render: (r: Shipment) => (r.total === null ? "—" : f.money(r.total, { unit: false })) }] : []),
  ];
  return (
    <section className="purchases">
      <Link to="/purchases" className="purchase__back">
        ← {t("shipments.backToPurchases")}
      </Link>
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("shipments.title")}</h1>
        </div>
        <span className="purchases__actions">
          {canManage && (
            <Button variant="primary" onClick={() => setAdding(true)}>
              {t("shipments.add")}
            </Button>
          )}
        </span>
      </header>
      <p className="caption">{t("shipments.lead")}</p>
      <div className="purchases__panel purchases__panel--shipments">
        {query.isError ? (
          <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
        ) : !query.data ? (
          <Skeleton label={t("common.loading")} lines={4} />
        ) : query.data.items.length === 0 ? (
          <EmptyState title={t("shipments.empty")} text={t("shipments.emptyText")} action={canManage ? <Button onClick={() => setAdding(true)}>{t("shipments.add")}</Button> : undefined} />
        ) : (
          <>
            <DataTable caption={t("shipments.title")} columns={columns} rows={query.data.items} rowKey={(r) => r.id} />
            <Pagination
              page={query.data.page}
              pages={query.data.pages}
              total={query.data.total}
              size={size}
              onPage={setPage}
              onSize={(n) => {
                setSize(n);
                setPage(1);
              }}
            />
          </>
        )}
      </div>
      {adding && <ShipmentForm orgId={org.id} shipment={null} onClose={() => setAdding(false)} onSaved={(saved) => void navigate({ to: "/shipments/$shipmentId", params: { shipmentId: saved.shipment.id } })} />}
    </section>
  );
}
