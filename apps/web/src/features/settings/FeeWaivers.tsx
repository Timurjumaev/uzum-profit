// Uzum bonus davrlari bo'limi (M16, B4.8; ADR-031): to'liq ro'yxat (boshlanish sanasi bo'yicha yangisi tepada),
// qo'shish, tahrirlash va o'chirish. O'zgartirish — egasi va menejer (`manage_settings`); boshqalar faqat ko'radi.
import { useMutation, useQuery } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { deleteWaiver, feeWaiversQuery } from "../../app/query";
import { Badge, Banner, Button, DataTable, Dialog, EmptyState, useToast, type Column } from "../../components/ui";
import type { Waiver as WaiverOut } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { useKindLabel, useRefresh, useShopName, WaiverForm, type WaiverDraft } from "../pnl/Waivers";

type Props = { orgId: string; canManage: boolean };

export function FeeWaivers({ orgId, canManage }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const kindLabel = useKindLabel();
  const shopName = useShopName(orgId);
  const refresh = useRefresh(orgId);

  const waivers = useQuery(feeWaiversQuery(orgId));
  const [draft, setDraft] = useState<{ id?: string; initial: WaiverDraft } | null>(null);
  const [deleting, setDeleting] = useState<WaiverOut | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => deleteWaiver(orgId, id),
    onSuccess: async () => {
      await refresh();
      toast.show(t("pnl.waivers.deleted"), "positive");
      setDeleting(null);
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });

  const items = useMemo(() => {
    const list = [...(waivers.data?.items ?? [])];
    return list.sort((a, b) => b.start_on.localeCompare(a.start_on) || b.created_at.localeCompare(a.created_at));
  }, [waivers.data?.items]);

  const today = new Date().toISOString().slice(0, 10);
  const emptyDraft = (): WaiverDraft => ({
    shop: "",
    start: today,
    end: today,
    kinds: ["sale_logistics"],
    reason: "",
    source: "manual",
  });

  const columns: Column<WaiverOut>[] = [
    {
      key: "period",
      header: t("settings.waivers.col.period"),
      render: (w) => f.period(w.start_on, w.end_on),
    },
    {
      key: "shop",
      header: t("settings.waivers.col.shop"),
      render: (w) => shopName(w.shop_id),
    },
    {
      key: "kinds",
      header: t("settings.waivers.col.kinds"),
      render: (w) => w.kinds.map(kindLabel).join(", "),
    },
    {
      key: "reason",
      header: t("settings.waivers.col.reason"),
      render: (w) => w.reason || "—",
    },
    {
      key: "source",
      header: t("settings.waivers.col.source"),
      render: (w) => (w.source === "detected" ? t("settings.waivers.source.detected") : t("settings.waivers.source.manual")),
    },
    {
      key: "status",
      header: t("settings.waivers.col.status"),
      render: (w) =>
        w.dismissed ? (
          <Badge tone="negative">
            <CircleAlert size={12} aria-hidden />
            {t("settings.waivers.dismissed")}
          </Badge>
        ) : (
          "—"
        ),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("settings.waivers.col.actions"),
            render: (w: WaiverOut) => (
              <span className="settings-actions">
                {!w.dismissed && (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setDraft({
                        id: w.id,
                        initial: {
                          shop: w.shop_id ?? "",
                          start: w.start_on,
                          end: w.end_on,
                          kinds: w.kinds,
                          reason: w.reason,
                          source: (w.source as WaiverDraft["source"]) ?? "manual",
                        },
                      })
                    }
                    aria-label={`${t("settings.waivers.edit")}: ${f.period(w.start_on, w.end_on)}`}
                  >
                    {t("settings.waivers.edit")}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  onClick={() => setDeleting(w)}
                  aria-label={`${t("pnl.waivers.delete")}: ${f.period(w.start_on, w.end_on)}`}
                >
                  {t("pnl.waivers.delete")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];

  return (
    <section className="settings-section" aria-labelledby="settings-waivers-title">
      <div className="settings-section__head">
        <div>
          <h2 id="settings-waivers-title" className="h3">
            {t("settings.waivers.title")}
          </h2>
          <p className="caption">{t("settings.waivers.lead")}</p>
        </div>
        {canManage && items.length > 0 && (
          <Button onClick={() => setDraft({ initial: emptyDraft() })}>
            {t("settings.waivers.add")}
          </Button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title={t("settings.waivers.empty.title")}
          text={t("settings.waivers.empty.text")}
          action={
            canManage ? (
              <Button onClick={() => setDraft({ initial: emptyDraft() })}>
                {t("settings.waivers.add")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          caption={t("settings.waivers.caption")}
          columns={columns}
          rows={items}
          rowKey={(w) => w.id}
        />
      )}

      {draft && (
        <WaiverForm
          orgId={orgId}
          id={draft.id}
          initial={draft.initial}
          onClose={() => setDraft(null)}
        />
      )}

      {deleting && (
        <Dialog
          open
          title={t("settings.waivers.deleteDialog.title")}
          onClose={() => setDeleting(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setDeleting(null)}>
                {t("settings.waivers.deleteDialog.cancel")}
              </Button>
              <Button
                variant="destructive"
                loading={remove.isPending}
                onClick={() => remove.mutate(deleting.id)}
              >
                {t("settings.waivers.deleteDialog.confirm")}
              </Button>
            </>
          }
        >
          {remove.isError && <Banner tone="negative" title={errorText(remove.error, t)} />}
          <p>{t("settings.waivers.deleteDialog.text")}</p>
        </Dialog>
      )}
    </section>
  );
}
