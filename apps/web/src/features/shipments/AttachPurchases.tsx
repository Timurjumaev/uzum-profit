// Kargoga xarid biriktirish (ADR-046, qo'shimcha): kargo sahifasida kargosiz (yoki boshqa kargodagi) xaridlardan bir
// nechtasini belgilab shu kargoga biriktiriladi. Xarid sahifasidagi "Kargo" tanlovining ko'zgusi: xarid bitta kargoga
// tegishli, kargo esa ko'p xaridga. Boshqa kargodagi xarid ko'chiriladi (eski va yangi kargo qayta hisoblanadi). Xaridlar
// ketma-ket biriktiriladi; biri xato bersa to'xtaydi va nechtasi biriktirilgani aytiladi (qolganlari tegilmaydi).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { purchasesQuery, updatePurchase } from "../../app/query";
import { Banner, Button, Dialog, EmptyState, Skeleton } from "../../components/ui";
import type { PurchaseRow } from "../../lib/api/types";

type Props = {
  orgId: string;
  shipmentId: string;
  onClose: () => void;
  /** Hammasi biriktirildi: oyna yopiladi, xabar chiqadi. */
  onAttached: (count: number) => void;
  /** Kamida bittasi biriktirildi (xato bilan to'xtagan bo'lsa ham): kargo va ro'yxatlar yangilanadi, oyna ochiq qoladi. */
  onChanged: () => void;
};

/** Ketma-ket biriktirishda biri xato berdi: nechtasi biriktirilgani va asl xato. */
class PartialAttach extends Error {
  constructor(
    readonly done: number,
    readonly cause: unknown,
  ) {
    super("partial attach");
  }
}

const label = (p: PurchaseRow, untitled: string) => [p.title ?? untitled, p.supplier_name].filter(Boolean).join(" · ");

export function AttachPurchases({ orgId, shipmentId, onClose, onAttached, onChanged }: Props) {
  const { t } = useTranslation();
  const purchases = useQuery(purchasesQuery(orgId, []));
  const [picked, setPicked] = useState<string[]>([]);
  // Kargosizlar birinchi (ko'pincha kerak bo'lgani), keyin boshqa kargodagilar; shu kargodagilar ro'yxatda yo'q.
  const rows = (purchases.data?.items ?? []).filter((p) => p.shipment_id !== shipmentId).sort((a, b) => Number(a.shipment_id !== null) - Number(b.shipment_id !== null));
  const attach = useMutation({
    mutationFn: async () => {
      let done = 0;
      try {
        for (const id of picked) {
          await updatePurchase(orgId, id, { shipment_id: shipmentId });
          done += 1;
        }
      } catch (error) {
        throw new PartialAttach(done, error);
      }
      return done;
    },
    onSuccess: onAttached,
    onError: (error) => {
      if (error instanceof PartialAttach && error.done > 0) {
        // Biriktirilganlar ro'yxatdan chiqadi; qolganlari belgilangan holda qoladi — qayta urinish mumkin.
        setPicked((x) => x.slice(error.done));
        onChanged();
      }
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (picked.length > 0) attach.mutate();
  };
  const toggle = (id: string, on: boolean) => setPicked((x) => (on ? [...x, id] : x.filter((y) => y !== id)));
  return (
    <Dialog
      open
      title={t("shipments.attach.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="attach-form" disabled={picked.length === 0} loading={attach.isPending}>
            {t("shipments.attach.save", { count: picked.length })}
          </Button>
        </>
      }
    >
      <form id="attach-form" className="purchase-form" onSubmit={submit}>
        {attach.isError && (
          <Banner
            tone="negative"
            title={t("shipments.attach.failed", {
              done: attach.error instanceof PartialAttach ? attach.error.done : 0,
              reason: errorText(attach.error instanceof PartialAttach ? attach.error.cause : attach.error, t),
            })}
          />
        )}
        <p className="caption">{t("shipments.attach.hint")}</p>
        {purchases.isError ? (
          <Banner tone="negative" title={errorText(purchases.error, t)} action={<Button onClick={() => void purchases.refetch()}>{t("common.retry")}</Button>} />
        ) : !purchases.data ? (
          <Skeleton label={t("common.loading")} lines={4} />
        ) : rows.length === 0 ? (
          <EmptyState title={t("shipments.attach.empty")} text={t("shipments.attach.emptyText")} />
        ) : (
          <fieldset className="purchase-form__lines">
            <legend className="ui-field__label">{t("shipments.col.purchases")}</legend>
            {rows.map((p) => (
              <label key={p.id}>
                <input type="checkbox" checked={picked.includes(p.id)} onChange={(e) => toggle(p.id, e.target.checked)} />
                <span className="purchase-form__choice">
                <span>{label(p, t("purchases.untitled"))}</span>
                <span className="caption">
                  {t(`purchases.stage.${p.stage}`)}
                  {" · "}
                  {p.shipment_id
                    ? t("shipments.attach.inOther", {
                        name: p.shipment_name || t("shipments.untitled"),
                      })
                    : t("shipments.attach.free")}
                </span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
      </form>
    </Dialog>
  );
}
