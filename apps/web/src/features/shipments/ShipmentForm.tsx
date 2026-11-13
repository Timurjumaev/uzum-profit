// Kargo shakli (yangi va tahrirlash, ADR-046): nomi, kargo kompaniyasi, Xitoy omborida / yo'lda / Toshkentga keldi sanalari,
// izoh. Sanalar kargodan olinadi: kargoga bog'langan hamma xaridda shu bosqichlar kargo bilan bir xil (bo'sh sana o'chiradi).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { carriersQuery, createShipment, updateShipment } from "../../app/query";
import { Banner, Button, Dialog, Select, TextInput, useToast } from "../../components/ui";
import type { Shipment, ShipmentDetail } from "../../lib/api/types";

const NONE = "";
type Draft = { title: string; carrier: string; cn: string; shipped: string; arrived: string; note: string };

const ordered = (d: Draft) => {
  const dates = [d.cn, d.shipped, d.arrived].filter(Boolean);
  return dates.every((x, i) => i === 0 || x >= dates[i - 1]!);
};

export function ShipmentForm({ orgId, shipment, onClose, onSaved }: { orgId: string; shipment: Shipment | null; onClose: () => void; onSaved: (d: ShipmentDetail) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const carriers = useQuery(carriersQuery(orgId));
  const [draft, setDraft] = useState<Draft>({
    title: shipment?.title ?? "",
    carrier: shipment?.carrier_id ?? NONE,
    cn: shipment?.cn_warehouse_on ?? "",
    shipped: shipment?.shipped_on ?? "",
    arrived: shipment?.arrived_on ?? "",
    note: shipment?.note ?? "",
  });
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const valid = ordered(draft);
  // ADR-061 §9: yangi kargoda sanalar so'ralmaydi; eski kargoda sanasi bo'lsa — tahrirlanadi (tamoyil 7).
  const showDates = shipment !== null && Boolean(shipment.cn_warehouse_on || shipment.shipped_on || shipment.arrived_on);
  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: draft.title.trim() || null,
        carrier_id: draft.carrier === NONE ? null : draft.carrier,
        ...(showDates ? { cn_warehouse_on: draft.cn || null, shipped_on: draft.shipped || null, arrived_on: draft.arrived || null } : {}),
        note: draft.note.trim() || null,
      };
      return shipment ? updateShipment(orgId, shipment.id, body) : createShipment(orgId, body);
    },
    onSuccess: async (saved) => {
      // Sanalar va xarajatlar xaridlarga ta'sir qiladi: ro'yxatlar va xarid sahifalari eskiradi.
      await Promise.all([["shipments"], ["purchases"], ["pnl"], ["dashboard"], ["inventory"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
      toast.show(t(shipment ? "shipments.saved" : "shipments.created"), "positive");
      onSaved(saved);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={shipment ? t("shipments.editTitle") : t("shipments.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="shipment-form" disabled={!valid} loading={save.isPending}>
            {t("shipments.save")}
          </Button>
        </>
      }
    >
      <form id="shipment-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <TextInput label={t("shipments.fields.title")} help={t("shipments.fields.titleHint")} optional value={draft.title} onValueChange={(title) => patch({ title })} maxLength={300} />
        <Select
          label={t("purchases.fields.carrier")}
          value={draft.carrier}
          onValueChange={(carrier) => patch({ carrier })}
          options={[{ value: NONE, label: t("purchases.fields.none") }, ...(carriers.data ?? []).map((c) => ({ value: c.id, label: c.name }))]}
        />
        {showDates && (
          <>
            <p className="caption">{t("shipments.datesHint")}</p>
            {!valid && <Banner tone="warning" title={t("purchases.datesOrder")} />}
            <div className="purchase-form__dates">
              <TextInput label={t("purchases.stage.cn_warehouse")} type="date" optional value={draft.cn} onValueChange={(cn) => patch({ cn })} />
              <TextInput label={t("purchases.stage.shipped")} type="date" optional value={draft.shipped} onValueChange={(shipped) => patch({ shipped })} />
              <TextInput label={t("purchases.stage.arrived")} type="date" optional value={draft.arrived} onValueChange={(arrived) => patch({ arrived })} />
            </div>
          </>
        )}
        <TextInput label={t("purchases.fields.note")} optional value={draft.note} onValueChange={(note) => patch({ note })} maxLength={500} />
      </form>
    </Dialog>
  );
}
