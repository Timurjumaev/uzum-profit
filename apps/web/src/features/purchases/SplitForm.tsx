// "Xaridni ikkiga bo'lish" (TM4, ADR-061 §6): xarid qismlab keladi — har qatorda "keyin keladi" dona; ular yangi xaridga
// o'tadi ("Yo'lda" qoladi), chiqimlar dona bo'yicha serverda bo'linadi (F20), keyin tahrirlanadi. Kelgan qism sanaladi.
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { splitPurchase } from "../../app/query";
import { Banner, Button, Dialog, NumberInput } from "../../components/ui";
import type { PurchaseDetail } from "../../lib/api/types";
import { lineLabel } from "./ComponentForm";

export function SplitForm({ orgId, detail, onClose, onSaved }: { orgId: string; detail: PurchaseDetail; onClose: () => void; onSaved: (d: PurchaseDetail, newId: string) => void }) {
  const { t } = useTranslation();
  const [later, setLater] = useState<Record<string, string | null>>({});
  const moves = detail.lines.map((l) => ({ line: l, qty: Number(later[l.id] ?? 0) })).filter((x) => x.qty > 0);
  const totalOrdered = detail.lines.reduce((acc, l) => acc + l.ordered_qty, 0);
  const totalMoved = moves.reduce((acc, x) => acc + x.qty, 0);
  const bad = detail.lines.some((l) => {
    const v = later[l.id];
    return v !== undefined && v !== null && v !== "" && (!Number.isInteger(Number(v)) || Number(v) < 0 || Number(v) > l.ordered_qty);
  });
  const valid = !bad && moves.length > 0 && totalMoved < totalOrdered;
  const save = useMutation({
    mutationFn: () => splitPurchase(orgId, detail.purchase.id, { lines: moves.map((x) => ({ line_id: x.line.id, qty: x.qty })) }),
    onSuccess: (out) => onSaved(out.purchase, out.new_purchase_id),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("purchases.split.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="split-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.split.save")}
          </Button>
        </>
      }
    >
      <form id="split-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <p className="caption">{t("purchases.split.hint")}</p>
        {detail.lines.map((l) => (
          <NumberInput
            key={l.id}
            label={`${lineLabel(l)} · ${t("purchases.count.ordered", { count: l.ordered_qty })}`}
            help={t("purchases.split.later")}
            optional
            value={later[l.id] ?? null}
            onValueChange={(v) => setLater((x) => ({ ...x, [l.id]: v }))}
            digits={0}
          />
        ))}
        {(bad || (moves.length > 0 && totalMoved >= totalOrdered)) && <Banner tone="warning" title={t("purchases.split.invalid")} />}
      </form>
    </Dialog>
  );
}
