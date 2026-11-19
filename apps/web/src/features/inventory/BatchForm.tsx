// Odatiy partiya hajmi (B5.2, F27): tavsiya miqdor shu sonning karralisigacha yuqoriga yaxlitlanadi (masalan, kartonda 50 dona).
// Bo'sh — yaxlitlanmaydi (1 dona). Faqat tavsiyaga ta'sir qiladi: tannarx va hisobotlarga tegmaydi.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { setOrderBatch } from "../../app/query";
import { Banner, Button, Dialog, NumberInput, useToast } from "../../components/ui";

export function BatchForm({ orgId, skuId, title, current, onClose }: { orgId: string; skuId: string; title: string; current: number | null; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const [value, setValue] = useState<string | null>(current === null ? null : String(current));
  const amount = value === null || value === "" ? null : Number(value);
  const valid = amount === null || (Number.isInteger(amount) && amount >= 1);
  const save = useMutation({
    mutationFn: () => setOrderBatch(orgId, skuId, amount),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "inventory"] });
      toast.show(t("inventory.batch.saved"), "positive");
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("inventory.batch.title", { name: title })}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("inventory.move.close")}
          </Button>
          <Button type="submit" form="order-batch-form" disabled={!valid} loading={save.isPending}>
            {t("inventory.batch.save")}
          </Button>
        </>
      }
    >
      <form id="order-batch-form" className="inventory-move" onSubmit={submit}>
        {save.error && <Banner tone="negative" title={errorText(save.error, t)} />}
        <p className="caption">{t("inventory.batch.hint")}</p>
        <NumberInput label={t("inventory.batch.label")} help={t("inventory.batch.help")} value={value} onValueChange={setValue} digits={0} suffix={t("inventory.unit")} />
      </form>
    </Dialog>
  );
}
