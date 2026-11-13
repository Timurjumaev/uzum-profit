// Kargo sahifasi (M9, ADR-046; 04 §7.4): sanalar (Xitoy omborida / yo'lda / keldi — kargoga bog'langan hamma xaridga
// o'tadi), kargodagi xaridlar (har biriga tushgan kargo ulushi), kargo xarajatlari (kurs bilan; hamma tovarlarga bitta
// taqsimotda bo'linadi) va tovarlar (har tovarga ulush va dona boshiga). Hamma raqam API'dan (F20); bu yerda hisob yo'q.
// Omborchi summalarni ko'rmaydi: xaridlar, tovarlar va sanalar.
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createShipmentComponent, currentOrg, deleteShipment, deleteShipmentComponent, meQuery, shipmentQuery, updatePurchase, updateShipmentComponent } from "../../app/query";
import { Badge, Banner, Button, DataTable, Dialog, EmptyState, Skeleton, useToast, type Column } from "../../components/ui";
import type { CostComponent, ShipmentDetail, ShipmentLine, ShipmentPurchase } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { ComponentForm } from "../purchases/ComponentForm";
import { useComponentColumns } from "../purchases/componentColumns";
import { isEstimated, isInfoFlag, SHIPMENT_KINDS, visibleFlags } from "../purchases/model";
import { MANAGE_ROLES } from "../purchases/Purchases";
import { AttachPurchases } from "./AttachPurchases";
import { ShipmentForm } from "./ShipmentForm";

type Editing = { kind: "header" } | { kind: "delete" } | { kind: "attach" } | { kind: "component"; component: CostComponent | null };

function BackLink() {
  const { t } = useTranslation();
  return (
    <Link to="/shipments" className="purchase__back">
      ← {t("shipments.back")}
    </Link>
  );
}

export function ShipmentPage() {
  const { t } = useTranslation();
  const { shipmentId } = useParams({ strict: false }) as { shipmentId: string };
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const query = useQuery(shipmentQuery(org.id, shipmentId));
  if (query.isError)
    return (
      <section className="purchase">
        <BackLink />
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  if (!query.data) return <Skeleton label={t("common.loading")} lines={10} />;
  return <ShipmentView orgId={org.id} detail={query.data} canManage={MANAGE_ROLES.includes(org.role)} />;
}

function ShipmentView({ orgId, detail, canManage }: { orgId: string; detail: ShipmentDetail; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Editing | null>(null);
  const s = detail.shipment;
  const key = shipmentQuery(orgId, s.id).queryKey;
  const amounts = detail.amounts;
  /** Yozuv javobi — yangi taqsimot bilan butun kargo: keshga qo'yiladi; xaridlar, ro'yxatlar va hisobotlar eskiradi. */
  const applied = async (next: ShipmentDetail, message: string) => {
    client.setQueryData(key, next);
    setEditing(null);
    toast.show(message, "positive");
    await Promise.all(
      [["shipments", "list"], ["purchases"], ["pnl"], ["dashboard"], ["skus"], ["sku"], ["inventory"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })),
    );
  };
  /** Xaridlar biriktirildi/ko'chirildi: kargo (xaridlar, ulushlar) qayta o'qiladi, ro'yxatlar va hisobotlar eskiradi. */
  const refresh = () => Promise.all([["shipments"], ["purchases"], ["pnl"], ["dashboard"], ["skus"], ["sku"], ["inventory"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
  /** Xaridni kargodan ajratish (xarid o'z holicha qoladi; kargo va qolgan xaridlar tannarxi qayta hisoblanadi). */
  const detach = useMutation({
    mutationFn: (purchaseId: string) => updatePurchase(orgId, purchaseId, { shipment_id: null }),
    onSuccess: async () => {
      toast.show(t("shipments.link.detached"), "positive");
      await refresh();
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const removeComponent = useMutation({
    mutationFn: (id: string) => deleteShipmentComponent(orgId, s.id, id),
    onSuccess: (next) => applied(next, t("purchases.components.deleted")),
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const componentColumns = useComponentColumns(
    canManage
      ? { onEdit: (c) => setEditing({ kind: "component", component: c }), onDelete: (c) => removeComponent.mutate(c.id), deleting: removeComponent.isPending ? (removeComponent.variables ?? null) : null }
      : undefined,
  );
  const date = (d: string | null) => (d ? f.date(d) : "—");
  const money = (v: string | null) => (v === null ? "—" : f.money(v, { unit: false }));
  const flagsOf = (rows: ShipmentLine[]) => visibleFlags([...new Set(rows.flatMap((l) => l.flags))]);
  const flags = flagsOf(detail.lines);

  const purchaseColumns: Column<ShipmentPurchase>[] = [
    {
      key: "purchase",
      header: t("purchases.col.purchase"),
      render: (r) => (
        <Link to="/purchases/$purchaseId" params={{ purchaseId: r.id }} className="purchase-cell__title">
          {r.title ?? t("purchases.untitled")}
        </Link>
      ),
    },
    { key: "supplier", header: t("purchases.col.supplier"), render: (r) => r.supplier_name ?? "—" },
    { key: "stage", header: t("purchases.col.path"), render: (r) => <Badge tone={r.stage === "closed" ? "positive" : r.stage === "draft" ? "neutral" : "info"}>{t(`purchases.stage.${r.stage}`)}</Badge> },
    { key: "units", header: t("purchases.col.units"), numeric: true, render: (r) => f.number(r.units) },
    ...(amounts
      ? [
          { key: "share", header: t("shipments.col.share"), numeric: true, render: (r: ShipmentPurchase) => (r.error ? <Badge tone="negative">{t("purchases.notCalculated")}</Badge> : money(r.share)) },
          { key: "total", header: t("purchases.col.total"), numeric: true, render: (r: ShipmentPurchase) => money(r.total) },
          {
            key: "unit",
            header: t("purchases.col.unitCost"),
            numeric: true,
            render: (r: ShipmentPurchase) => (r.unit_cost === null ? "—" : money(r.unit_cost)),
          },
        ]
      : []),
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (r: ShipmentPurchase) => (
              <span className="expenses-actions">
                <Button variant="ghost" loading={detach.isPending && detach.variables === r.id} onClick={() => detach.mutate(r.id)} aria-label={`${t("shipments.detach")}: ${r.title ?? t("purchases.untitled")}`}>
                  {t("shipments.detach")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];
  const lineColumns: Column<ShipmentLine>[] = [
    { key: "name", header: t("purchases.lines.col.item"), render: (l) => l.name ?? "—" },
    { key: "purchase", header: t("purchases.col.purchase"), render: (l) => l.purchase_title ?? t("purchases.untitled") },
    { key: "qty", header: t("purchases.lines.col.received"), numeric: true, render: (l) => f.number(l.qty) },
    { key: "weight", header: t("purchases.lines.col.weight"), numeric: true, render: (l) => (l.unit_weight === null ? "—" : t("purchases.lines.kg", { value: f.number(l.unit_weight, { digits: 3, trim: true }) })) },
    ...(amounts
      ? [
          { key: "share", header: t("shipments.col.share"), numeric: true, render: (l: ShipmentLine) => money(l.share) },
          { key: "per", header: t("shipments.col.perUnit"), numeric: true, render: (l: ShipmentLine) => money(l.share_per_unit) },
        ]
      : []),
  ];
  const lineChoices = detail.lines.map((l) => ({ id: l.id, label: [l.purchase_title ?? t("purchases.untitled"), l.name ?? "—"].join(" · ") }));

  return (
    <section className="purchase">
      <BackLink />
      <header className="purchase__head">
        <div>
          <h1 className="h2">{s.title || t("shipments.untitled")}</h1>
          <p className="caption">
            {s.carrier_name ?? t("shipments.noCarrier")}
            {` · ${t("shipments.datesLine", { cn: date(s.cn_warehouse_on), shipped: date(s.shipped_on), arrived: date(s.arrived_on) })}`}
          </p>
          {s.note && <p className="caption">{s.note}</p>}
        </div>
        {canManage && (
          <div className="purchase__actions">
            <Button variant="secondary" onClick={() => setEditing({ kind: "header" })}>
              {t("purchases.edit")}
            </Button>
            <Button variant="ghost" onClick={() => setEditing({ kind: "delete" })}>
              {t("purchases.delete")}
            </Button>
          </div>
        )}
      </header>

      {detail.error && (
        <Banner tone="negative" title={t("shipments.error", { reason: detail.error })}>
          {t("purchases.errorHint")}
        </Banner>
      )}
      {detail.recalc_pending && amounts && (
        <Banner tone="info" title={t("purchases.pending")}>
          {t("purchases.pendingText")}
        </Banner>
      )}
      {!amounts && (
        <Banner tone="info" title={t("purchases.noAmounts")}>
          {t("purchases.noAmountsText")}
        </Banner>
      )}

      <div className="purchase__layout">
        <div className="purchase__main">
          <section aria-labelledby="shipment-purchases-title" className="purchase__block">
            <div className="purchase__section-head">
              <h2 id="shipment-purchases-title" className="h3">
                {t("shipments.purchases")}
              </h2>
              {canManage && <Button onClick={() => setEditing({ kind: "attach" })}>{t("shipments.attach.button")}</Button>}
            </div>
            {detail.purchases.length === 0 ? (
              <EmptyState title={t("shipments.noPurchases")} text={t("shipments.noPurchasesText")} />
            ) : (
              <DataTable caption={t("shipments.purchases")} density="compact" columns={purchaseColumns} rows={detail.purchases} rowKey={(r) => r.id} />
            )}
          </section>
          {amounts && (
            <section aria-labelledby="shipment-components-title" className="purchase__block">
              <div className="purchase__section-head">
                <h2 id="shipment-components-title" className="h3">
                  {t("shipments.costs")}
                </h2>
                {canManage && (
                  <Button onClick={() => setEditing({ kind: "component", component: null })} disabled={detail.lines.length === 0}>
                    {t("purchases.components.add")}
                  </Button>
                )}
              </div>
              {detail.components.length === 0 ? (
                <EmptyState title={t("shipments.noCosts")} text={t(detail.lines.length === 0 ? "shipments.noCostsNoLines" : "shipments.noCostsText")} />
              ) : (
                <DataTable caption={t("shipments.costs")} density="compact" columns={componentColumns} rows={detail.components} rowKey={(c) => c.id} />
              )}
            </section>
          )}
          {detail.lines.length > 0 && (
            <section aria-labelledby="shipment-lines-title" className="purchase__block">
              <div className="purchase__section-head">
                <h2 id="shipment-lines-title" className="h3">
                  {t("shipments.lines")}
                </h2>
              </div>
              <DataTable caption={t("shipments.lines")} density="compact" columns={lineColumns} rows={detail.lines} rowKey={(l) => l.id} />
            </section>
          )}
        </div>
        <aside className="purchase__cost" aria-label={t("shipments.summary")}>
          <h2 className="h3">{t("shipments.summary")}</h2>
          <dl className="purchase__totals">
            <div>
              <dt>{t("shipments.col.purchases")}</dt>
              <dd className="num">{f.number(s.purchase_count)}</dd>
            </div>
            <div>
              <dt>{t("purchases.col.units")}</dt>
              <dd className="num">{f.number(s.units)}</dd>
            </div>
            {amounts && (
              <div>
                <dt>{t("shipments.col.total")}</dt>
                <dd className="num">{money(s.total)}</dd>
              </div>
            )}
          </dl>
          {amounts && Object.keys(detail.by_kind).length > 1 && (
            <ul className="purchase__kinds">
              {Object.entries(detail.by_kind).map(([kind, v]) => (
                <li key={kind}>
                  <span>{t(`purchases.components.kind.${kind}`)}</span>
                  <span className="num">{f.money(v, { unit: false })}</span>
                </li>
              ))}
            </ul>
          )}
          {flags.length > 0 && (
            <ul className="purchase__flags">
              {flags.map((flag) => (
                <li key={flag}>
                  <Badge tone={isInfoFlag(flag) ? "info" : "warning"}>{flag === "cbu_rate" ? t("purchases.components.rateLabel.cbu") : isInfoFlag(flag) ? t("purchases.cost.note") : t("terms.estimated")}</Badge> {t(`purchases.cost.flag.${flag}`)}
                </li>
              ))}
            </ul>
          )}
          <p className="caption">{t("shipments.splitNote")}</p>
          {isEstimated(flags) && <p className="caption">{t("shipments.estimatedNote")}</p>}
        </aside>
      </div>

      {editing?.kind === "header" && <ShipmentForm orgId={orgId} shipment={s} onClose={() => setEditing(null)} onSaved={(d) => void applied(d, t("shipments.saved"))} />}
      {editing?.kind === "component" && (
        <ComponentForm
          component={editing.component}
          lines={lineChoices}
          kinds={SHIPMENT_KINDS}
          submit={(body, id) => (id ? updateShipmentComponent(orgId, s.id, id, body) : createShipmentComponent(orgId, s.id, body))}
          onClose={() => setEditing(null)}
          onSaved={(d) => void applied(d, t("purchases.components.saved"))}
        />
      )}
      {editing?.kind === "attach" && (
        <AttachPurchases
          orgId={orgId}
          shipmentId={s.id}
          onClose={() => setEditing(null)}
          onChanged={() => void refresh()}
          onAttached={(count) => {
            setEditing(null);
            toast.show(t("shipments.attach.saved", { count }), "positive");
            void refresh();
          }}
        />
      )}
      {editing?.kind === "delete" && <DeleteDialog orgId={orgId} shipmentId={s.id} hasPurchases={s.purchase_count > 0} onClose={() => setEditing(null)} />}
    </section>
  );
}

function DeleteDialog({ orgId, shipmentId, hasPurchases, onClose }: { orgId: string; shipmentId: string; hasPurchases: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const navigate = useNavigate();
  const remove = useMutation({
    mutationFn: () => deleteShipment(orgId, shipmentId),
    onSuccess: async () => {
      client.removeQueries({ queryKey: shipmentQuery(orgId, shipmentId).queryKey });
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "shipments"] });
      toast.show(t("shipments.deleted"), "positive");
      void navigate({ to: "/shipments" });
    },
  });
  return (
    <Dialog
      open
      title={t("shipments.deleteTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button variant="destructive" loading={remove.isPending} disabled={hasPurchases} onClick={() => remove.mutate()}>
            {t("purchases.delete")}
          </Button>
        </>
      }
    >
      {remove.isError && <Banner tone="negative" title={errorText(remove.error, t)} />}
      <p>{hasPurchases ? t("shipments.deleteBlocked") : t("shipments.deleteText")}</p>
    </Dialog>
  );
}
