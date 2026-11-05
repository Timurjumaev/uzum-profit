// Xaridni kargoga biriktirish (ADR-046, qo'shimcha): xarid sahifasidagi "Yangi xarajat" oynasida Turi = Kargo tanlansa,
// summa o'rniga kargolar ro'yxati chiqadi (holati va sanalari bilan) va xarid shu kargoga biriktiriladi — xarajat
// komponenti yaratilmaydi: kargo narxi kargo sahifasida bir marta kiritiladi. Biriktirilgan kargoni almashtirish yoki
// ajratish ham shu yerda; "Yangi kargo…" ro'yxat bo'sh bo'lsa ham yo'l ochiq qoladi.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { createShipment, shipmentsQuery, updatePurchase } from "../../app/query";
import { TextInput } from "../../components/ui";
import type { PurchaseDetail, PurchaseRow, Shipment } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

const NEW = "__new";
const DETACH = "__detach";

export type ShipmentLinkProps = {
  orgId: string;
  purchase: PurchaseRow;
  onLinked: (detail: PurchaseDetail) => void;
};

/** Kargo holati — sanalaridan: eng oxirgi to'ldirilgan bosqich (keldi > yo'lda > Xitoy omborida). */
export function shipmentStatus(s: Pick<Shipment, "cn_warehouse_on" | "shipped_on" | "arrived_on">) {
  if (s.arrived_on) return { stage: "arrived", on: s.arrived_on } as const;
  if (s.shipped_on) return { stage: "shipped", on: s.shipped_on } as const;
  if (s.cn_warehouse_on) return { stage: "cn_warehouse", on: s.cn_warehouse_on } as const;
  return null;
}

/** Kargo tanlovi holati va saqlash: `link` berilmasa (kargo sahifasi) ro'yxat so'ralmaydi. */
export function useShipmentLink(link: ShipmentLinkProps | undefined) {
  const client = useQueryClient();
  const shipments = useQuery({
    ...shipmentsQuery(link?.orgId ?? ""),
    enabled: link !== undefined,
  });
  const [choice, setChoice] = useState<string>(link?.purchase.shipment_id ?? "");
  const [newName, setNewName] = useState("");
  const current = link?.purchase.shipment_id ?? null;
  const valid = link !== undefined && choice !== "" && choice !== current && (choice !== NEW || newName.trim() !== "");
  const save = useMutation({
    mutationFn: async () => {
      let shipmentId: string | null = choice === DETACH ? null : choice;
      if (choice === NEW) shipmentId = (await createShipment(link!.orgId, { title: newName.trim() })).shipment.id;
      return updatePurchase(link!.orgId, link!.purchase.id, {
        shipment_id: shipmentId,
      });
    },
    onSuccess: async (detail) => {
      await client.invalidateQueries({
        queryKey: ["orgs", link!.orgId, "shipments"],
      });
      link!.onLinked(detail);
    },
  });
  return {
    shipments: shipments.data?.items ?? [],
    choice,
    setChoice,
    newName,
    setNewName,
    current,
    valid,
    save,
    detaching: choice === DETACH,
  };
}

export function ShipmentLinkFields({ state }: { state: ReturnType<typeof useShipmentLink> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { shipments, choice, setChoice, newName, setNewName, current } = state;
  const option = (value: string, title: string, meta?: string, note?: string) => (
    <label key={value}>
      <input type="radio" name="shipment-link" checked={choice === value} onChange={() => setChoice(value)} /> {title}
      {meta && <span className="caption"> · {meta}</span>}
      {note && choice === value && <span className="caption purchase-form__note">{note}</span>}
    </label>
  );
  return (
    <>
      <fieldset className="purchase-form__modes">
        <legend className="ui-field__label">{t("shipments.link.legend")}</legend>
        <p className="caption">{t("shipments.link.hint")}</p>
        {current && option(DETACH, t("shipments.link.detach"))}
        {shipments.map((s) => {
          const status = shipmentStatus(s);
          const meta = [
            s.id === current ? t("shipments.link.current") : null,
            s.carrier_name,
            status ? `${t(`purchases.stage.${status.stage}`)} ${f.date(status.on)}` : t("shipments.link.noDates"),
          ]
            .filter(Boolean)
            .join(" · ");
          return option(s.id, s.title || t("shipments.untitled"), meta, status?.stage === "arrived" ? t("shipments.link.arrivedNote") : undefined);
        })}
        {option(NEW, t("shipments.link.newOption"))}
      </fieldset>
      {choice === NEW && <TextInput label={t("shipments.link.newName")} value={newName} onValueChange={setNewName} maxLength={300} />}
    </>
  );
}
