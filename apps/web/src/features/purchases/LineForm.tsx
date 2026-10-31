// Xarid qatori shakli (M9): mavjud tovar (qidiruv bilan) yoki "yangi tovar" (vaqtinchalik nom, 1688 havolasi, rasm),
// variant, buyurtma va qabul donasi (bo'sh — qabul qilinmagan), dona narxi valyutada (summalar ruxsati bilan), dona
// vazni va hajmi (kargoni bo'lish uchun, ixtiyoriy).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createLine, itemsQuery, updateLine } from "../../app/query";
import { Banner, Button, Combobox, Dialog, MoneyInput, NumberInput, Select, TextInput } from "../../components/ui";
import type { PurchaseDetail, PurchaseLine } from "../../lib/api/types";
import { CURRENCIES, type CurrencyCode } from "./model";

type Mode = "item" | "new";
type Draft = {
  mode: Mode;
  item: string | null;
  tempName: string;
  url: string;
  imageUrl: string;
  variant: string;
  ordered: string | null;
  received: string | null;
  price: string | null;
  currency: CurrencyCode;
  weight: string | null;
  volume: string | null;
};

function draftOf(line: PurchaseLine | null): Draft {
  return {
    mode: line && !line.item_id ? "new" : "item",
    item: line?.item_id ?? null,
    tempName: line?.temp_name ?? "",
    url: line?.url ?? "",
    imageUrl: line?.image_url ?? "",
    variant: line?.variant ?? "",
    ordered: line ? String(line.ordered_qty) : null,
    received: line?.received_qty == null ? null : String(line.received_qty),
    price: line?.unit_price ?? null,
    currency: ((line?.currency as CurrencyCode | null) ?? "CNY") as CurrencyCode,
    weight: line?.unit_weight ?? null,
    volume: line?.unit_volume ?? null,
  };
}

const text = (v: string) => (v.trim() === "" ? null : v.trim());

type Props = { orgId: string; purchaseId: string; line: PurchaseLine | null; amounts: boolean; onClose: () => void; onSaved: (d: PurchaseDetail) => void };

export function LineForm({ orgId, purchaseId, line, amounts, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const items = useQuery(itemsQuery(orgId, ""));
  const [draft, setDraft] = useState(() => draftOf(line));
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const ordered = Number(draft.ordered);
  const valid =
    (draft.mode === "item" ? draft.item !== null : draft.tempName.trim() !== "") &&
    Number.isInteger(ordered) &&
    ordered >= 1 &&
    (draft.received === null || (Number.isInteger(Number(draft.received)) && Number(draft.received) >= 0));
  const save = useMutation({
    mutationFn: () => {
      const body = {
        item_id: draft.mode === "item" ? draft.item : null,
        temp_name: draft.mode === "new" ? text(draft.tempName) : null,
        url: draft.mode === "new" ? text(draft.url) : null,
        image_url: draft.mode === "new" ? text(draft.imageUrl) : null,
        variant: text(draft.variant),
        ordered_qty: ordered,
        received_qty: draft.received === null ? null : Number(draft.received),
        unit_weight: draft.weight,
        unit_volume: draft.volume,
        // Omborchi narxni ko'rmaydi va o'zgartirmaydi (API 403) — maydon yuborilmaydi.
        ...(amounts ? { unit_price: draft.price, currency: draft.price === null ? null : draft.currency } : {}),
      };
      return line ? updateLine(orgId, purchaseId, line.id, body) : createLine(orgId, purchaseId, body);
    },
    onSuccess: onSaved,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const options = (items.data?.items ?? []).map((i) => ({ value: i.id, label: i.name }));
  return (
    <Dialog
      open
      title={line ? t("purchases.lines.editTitle") : t("purchases.lines.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="line-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.save")}
          </Button>
        </>
      }
    >
      <form id="line-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <fieldset className="purchase-form__modes">
          <legend className="ui-field__label">{t("purchases.lines.item")}</legend>
          {(["item", "new"] as const).map((m) => (
            <label key={m}>
              <input type="radio" name="line-mode" checked={draft.mode === m} onChange={() => patch({ mode: m })} /> {t(`purchases.lines.mode.${m}`)}
            </label>
          ))}
        </fieldset>
        {draft.mode === "item" ? (
          <Combobox label={t("purchases.lines.item")} placeholder={t("purchases.lines.pickItem")} options={options} value={draft.item} onValueChange={(item) => patch({ item })} />
        ) : (
          <>
            <TextInput label={t("purchases.lines.tempName")} value={draft.tempName} onValueChange={(tempName) => patch({ tempName })} maxLength={200} />
            <TextInput label={t("purchases.lines.url")} optional type="url" value={draft.url} onValueChange={(url) => patch({ url })} maxLength={1000} />
            <TextInput label={t("purchases.lines.imageUrl")} optional type="url" value={draft.imageUrl} onValueChange={(imageUrl) => patch({ imageUrl })} maxLength={1000} />
          </>
        )}
        <TextInput label={t("purchases.lines.variant")} optional value={draft.variant} onValueChange={(variant) => patch({ variant })} maxLength={200} />
        <div className="purchase-form__row">
          <NumberInput label={t("purchases.lines.orderedQty")} value={draft.ordered} onValueChange={(v) => patch({ ordered: v })} digits={0} />
          <NumberInput label={t("purchases.lines.receivedQty")} optional help={t("purchases.lines.receivedHint")} value={draft.received} onValueChange={(v) => patch({ received: v })} digits={0} />
        </div>
        {amounts && (
          <div className="purchase-form__row">
            <MoneyInput label={t("purchases.lines.unitPrice")} optional currency={draft.currency} value={draft.price} onValueChange={(price) => patch({ price })} />
            <Select label={t("purchases.lines.currency")} value={draft.currency} onValueChange={(c) => patch({ currency: c as CurrencyCode })} options={CURRENCIES.map((c) => ({ value: c, label: c }))} />
          </div>
        )}
        <div className="purchase-form__row">
          <NumberInput label={t("purchases.lines.unitWeight")} optional help={t("purchases.lines.measureHint")} value={draft.weight} onValueChange={(weight) => patch({ weight })} />
          <NumberInput label={t("purchases.lines.unitVolume")} optional value={draft.volume} onValueChange={(volume) => patch({ volume })} />
        </div>
      </form>
    </Dialog>
  );
}
