// Uzum bonuslari (ADR-031): bonus davrlarining to'liq ro'yxati — qo'shish, tahrirlash, o'chirish. Bonus haqiqiy foydani
// o'zgartirmaydi, faqat belgilaydi. O'zgartirish — egasi va menejer (`manage_settings`); boshqalar faqat ko'radi.
// Forma P&L sahifasidagi bilan bir xil (`features/pnl/Waivers.tsx`).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { deleteWaiver, feeWaiversQuery } from "../../app/query";
import { Badge, Banner, Button, DataTable, EmptyState, Skeleton, useToast, type Column } from "../../components/ui";
import type { Waiver } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { ALL_SHOPS, useKindLabel, useRefresh, useShopName, WaiverForm, type WaiverDraft } from "../pnl/Waivers";
import { Confirm } from "./Confirm";

type Editing = { id?: string; draft: WaiverDraft };

const draftOf = (w: Waiver): WaiverDraft => ({ shop: w.shop_id ?? ALL_SHOPS, start: w.start_on, end: w.end_on, kinds: w.kinds, reason: w.reason, source: w.source === "detected" ? "detected" : "manual" });

export function FeeWaivers({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const kindLabel = useKindLabel();
  const shopName = useShopName(orgId);
  const refresh = useRefresh(orgId);
  const query = useQuery(feeWaiversQuery(orgId));
  const [editing, setEditing] = useState<Editing | null>(null);
  const [removing, setRemoving] = useState<Waiver | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => deleteWaiver(orgId, id),
    onSuccess: async () => {
      await refresh();
      toast.show(t("pnl.waivers.deleted"), "positive");
      setRemoving(null);
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const add = () => setEditing({ draft: { shop: ALL_SHOPS, start: todayTashkent(), end: todayTashkent(), kinds: ["sale_logistics"], reason: "", source: "manual" } });
  // Yangisi tepada (boshlanish sanasi bo'yicha); server tartibi ham shunday, lekin mijozda kafolatlanadi.
  const rows = [...(query.data?.items ?? [])].sort((a, b) => b.start_on.localeCompare(a.start_on));
  const columns: Column<Waiver>[] = [
    { key: "period", header: t("settings.waivers.col.period"), render: (w) => f.period(w.start_on, w.end_on) },
    { key: "shop", header: t("settings.waivers.col.shop"), render: (w) => shopName(w.shop_id) },
    { key: "kinds", header: t("settings.waivers.col.kinds"), render: (w) => w.kinds.map(kindLabel).join(", ") },
    { key: "reason", header: t("settings.waivers.col.reason"), render: (w) => w.reason || "—" },
    {
      key: "source",
      header: t("settings.waivers.col.source"),
      render: (w) =>
        w.dismissed ? <Badge tone="neutral">{t("settings.waivers.dismissed")}</Badge> : t(w.source === "detected" ? "settings.waivers.detected" : "settings.waivers.manual"),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("settings.col.actions"),
            render: (w: Waiver) => (
              <span className="settings-actions">
                {!w.dismissed && (
                  <Button size="sm" variant="ghost" onClick={() => setEditing({ id: w.id, draft: draftOf(w) })}>
                    {t("settings.edit")}
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setRemoving(w)}>
                  {t("settings.delete")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="settings-section" aria-labelledby="settings-waivers">
      <header className="settings-section__head">
        <h2 id="settings-waivers" className="h3">
          {t("settings.waivers.title")}
        </h2>
        {canManage && <Button onClick={add}>{t("settings.waivers.add")}</Button>}
      </header>
      <p className="caption">{t("settings.waivers.lead")}</p>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      ) : !query.data ? (
        <Skeleton label={t("common.loading")} lines={3} />
      ) : rows.length === 0 ? (
        <EmptyState title={t("settings.waivers.empty")} text={t("settings.waivers.emptyText")} action={canManage ? <Button onClick={add}>{t("settings.waivers.add")}</Button> : undefined} />
      ) : (
        <DataTable caption={t("settings.waivers.title")} columns={columns} rows={rows} rowKey={(w) => w.id} />
      )}
      {editing && <WaiverForm orgId={orgId} initial={editing.draft} id={editing.id} onClose={() => setEditing(null)} />}
      {removing && (
        <Confirm title={t("settings.waivers.deleteTitle")} action={t("settings.delete")} loading={remove.isPending} onConfirm={() => remove.mutate(removing.id)} onClose={() => setRemoving(null)}>
          {t("settings.waivers.deleteText", { period: f.period(removing.start_on, removing.end_on) })}
        </Confirm>
      )}
    </section>
  );
}
