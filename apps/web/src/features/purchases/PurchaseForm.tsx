// Xarid sarlavhasi shakli (yangi xarid va tahrirlash): nomi, yetkazib beruvchi, kargo, izoh; yangi xaridda — buyurtma
// sanasi. Yetkazib beruvchi / kargo ro'yxatda bo'lmasa shu yerda nomi bilan yaratiladi (to'liq kartochka — B5.1).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { carriersQuery, createCarrier, createPurchase, createSupplier, suppliersQuery, updatePurchase } from "../../app/query";
import { Banner, Button, Dialog, Select, TextInput, useToast } from "../../components/ui";
import type { PurchaseDetail } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";

const NONE = "";
const NEW = "__new";

type Draft = { title: string; supplier: string; newSupplier: string; carrier: string; newCarrier: string; orderedOn: string; note: string };

export function PurchaseForm({ orgId, detail, onClose, onSaved }: { orgId: string; detail: PurchaseDetail | null; onClose: () => void; onSaved: (detail: PurchaseDetail) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const suppliers = useQuery(suppliersQuery(orgId));
  const carriers = useQuery(carriersQuery(orgId));
  const p = detail?.purchase;
  const [draft, setDraft] = useState<Draft>({
    title: p?.title ?? "",
    supplier: p?.supplier_id ?? NONE,
    newSupplier: "",
    carrier: p?.carrier_id ?? NONE,
    newCarrier: "",
    orderedOn: detail ? "" : todayTashkent(),
    note: p?.note ?? "",
  });
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const valid = (draft.supplier !== NEW || draft.newSupplier.trim() !== "") && (draft.carrier !== NEW || draft.newCarrier.trim() !== "");
  const save = useMutation({
    mutationFn: async () => {
      let supplier_id = draft.supplier === NONE ? null : draft.supplier;
      if (draft.supplier === NEW) supplier_id = (await createSupplier(orgId, draft.newSupplier.trim())).id;
      let carrier_id = draft.carrier === NONE ? null : draft.carrier;
      if (draft.carrier === NEW) carrier_id = (await createCarrier(orgId, draft.newCarrier.trim())).id;
      const title = draft.title.trim() || null;
      const note = draft.note.trim() || null;
      if (detail) return updatePurchase(orgId, detail.purchase.id, { title, supplier_id, carrier_id, note });
      return createPurchase(orgId, { title, supplier_id, carrier_id, note, dates: draft.orderedOn ? { ordered: draft.orderedOn } : {} });
    },
    onSuccess: async (saved) => {
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "purchases"] });
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "suppliers"] });
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "carriers"] });
      toast.show(t(detail ? "purchases.saved" : "purchases.created"), "positive");
      onSaved(saved);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const options = (rows: Array<{ id: string; name: string }> | undefined, newLabel: string) => [
    { value: NONE, label: t("purchases.fields.none") },
    ...(rows ?? []).map((r) => ({ value: r.id, label: r.name })),
    { value: NEW, label: newLabel },
  ];
  return (
    <Dialog
      open
      title={detail ? t("purchases.editTitle") : t("purchases.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="purchase-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.save")}
          </Button>
        </>
      }
    >
      <form id="purchase-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <TextInput label={t("purchases.fields.title")} help={t("purchases.fields.titleHint")} optional value={draft.title} onValueChange={(title) => patch({ title })} maxLength={200} />
        <Select label={t("purchases.fields.supplier")} value={draft.supplier} onValueChange={(supplier) => patch({ supplier })} options={options(suppliers.data, t("purchases.fields.newSupplier"))} />
        {draft.supplier === NEW && <TextInput label={t("purchases.fields.newSupplierName")} value={draft.newSupplier} onValueChange={(newSupplier) => patch({ newSupplier })} maxLength={200} />}
        <Select label={t("purchases.fields.carrier")} value={draft.carrier} onValueChange={(carrier) => patch({ carrier })} options={options(carriers.data, t("purchases.fields.newCarrier"))} />
        {draft.carrier === NEW && <TextInput label={t("purchases.fields.newCarrierName")} value={draft.newCarrier} onValueChange={(newCarrier) => patch({ newCarrier })} maxLength={200} />}
        {!detail && <TextInput label={t("purchases.fields.orderedOn")} type="date" optional value={draft.orderedOn} onValueChange={(orderedOn) => patch({ orderedOn })} />}
        <TextInput label={t("purchases.fields.note")} optional value={draft.note} onValueChange={(note) => patch({ note })} maxLength={500} />
      </form>
    </Dialog>
  );
}
