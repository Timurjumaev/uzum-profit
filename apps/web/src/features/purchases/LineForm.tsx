// Xarid tovari shakli (M9, ADR-044): Uzumdagi tovar — SKU'lar ro'yxatidan (hammasi, holatidan qat'i nazar; tovari
// bo'lmasa server yaratadi) bir yoki bir nechta, yoki "yangi tovar" (vaqtinchalik nom, 1688 havolasi, rasm). Bir nechta
// SKU tanlansa — har biriga dona, narx/vazn/hajm hammasiga bir xil (keyin alohida tahrirlanadi). Buyurtma va qabul
// donasi (bo'sh — qabul qilinmagan), dona narxi valyutada (summalar ruxsati bilan), dona vazni va hajmi (kargoni
// bo'lish uchun, ixtiyoriy).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createLine, createLines, skuPickerQuery, updateLine } from "../../app/query";
import { Banner, Button, Combobox, Dialog, MoneyInput, NumberInput, Select, TextInput } from "../../components/ui";
import type { LineIn, PickerRow, PurchaseDetail, PurchaseLine } from "../../lib/api/types";
import { CURRENCIES, pickerKey, pickerLabel, pickerOptions, type CurrencyCode } from "./model";

type Mode = "item" | "new";
type Picked = { key: string; label: string; qty: string | null };
type Draft = {
  mode: Mode;
  choice: string | null; // tahrirda: tanlangan variant kaliti (`item:…` — hozirgi tovar, `sku:…` — SKU)
  picked: Picked[]; // yangi qo'shishda: tanlangan SKU'lar
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
    choice: line?.item_id ? `item:${line.item_id}` : null,
    picked: [],
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
const whole = (v: string | null, min: number) => v !== null && v !== "" && Number.isInteger(Number(v)) && Number(v) >= min;

type Props = {
  orgId: string;
  purchaseId: string;
  line: PurchaseLine | null;
  /** Partiyadagi tovarlar: takror tanlansa belgi chiqadi, taqiqlanmaydi (narxi boshqa bo'lishi mumkin). */
  existing: readonly PurchaseLine[];
  amounts: boolean;
  onClose: () => void;
  onSaved: (d: PurchaseDetail, count: number) => void;
};

export function LineForm({ orgId, purchaseId, line, existing, amounts, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const picker = useQuery(skuPickerQuery(orgId));
  const taken = useMemo(() => new Set(existing.flatMap((l) => (l.item_id && l.id !== line?.id ? [l.item_id] : []))), [existing, line]);
  const [draft, setDraft] = useState(() => draftOf(line));
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const rows = useMemo(() => picker.data?.rows ?? [], [picker.data]);
  const rowOf = useMemo(() => new Map<string, PickerRow>(rows.map((r) => [pickerKey(r), r])), [rows]);
  const options = useMemo(() => {
    const all = pickerOptions(rows, t, taken);
    if (!line?.item_id) return all;
    // Hozirgi tovar har doim tanlanadi (SKU'siz yoki ro'yxatda yo'q bo'lsa ham).
    return [{ value: `item:${line.item_id}`, label: line.item_name ?? "—", hint: t("purchases.lines.current"), keywords: "" }, ...all];
  }, [rows, t, taken, line]);
  const editing = line !== null;
  const many = !editing && draft.mode === "item";
  const single = editing || draft.mode === "new" || draft.picked.length === 1;
  const free = useMemo(() => options.filter((o) => !draft.picked.some((p) => p.key === o.value)), [options, draft.picked]);
  const pick = (key: string) => {
    const row = rowOf.get(key);
    if (!row || draft.picked.some((p) => p.key === key)) return;
    const variant = row.title && row.title !== pickerLabel(row) ? ` · ${row.title}` : "";
    patch({ picked: [...draft.picked, { key, label: `${pickerLabel(row)}${variant}`, qty: null }] });
  };
  const setQty = (key: string, qty: string | null) => patch({ picked: draft.picked.map((p) => (p.key === key ? { ...p, qty } : p)) });
  const received = draft.received === null || whole(draft.received, 0);
  const valid =
    received &&
    (draft.mode === "new"
      ? draft.tempName.trim() !== "" && whole(draft.ordered, 1)
      : many
        ? draft.picked.length > 0 && draft.picked.every((p) => whole(p.qty, 1))
        : draft.choice !== null && whole(draft.ordered, 1));
  const refOf = (key: string): Pick<LineIn, "sku_id" | "item_id"> => (key.startsWith("sku:") ? { sku_id: key.slice(4) } : { item_id: key.slice(5) });
  const save = useMutation({
    mutationFn: async (): Promise<{ detail: PurchaseDetail; count: number }> => {
      const common = {
        unit_weight: draft.weight,
        unit_volume: draft.volume,
        // Omborchi narxni ko'rmaydi va o'zgartirmaydi (API 403) — maydon yuborilmaydi.
        ...(amounts ? { unit_price: draft.price, currency: draft.price === null ? null : draft.currency } : {}),
      };
      const own = {
        variant: text(draft.variant),
        received_qty: draft.received === null ? null : Number(draft.received),
      };
      if (many) {
        const lines: LineIn[] = draft.picked.map((p) => ({
          ...refOf(p.key),
          ordered_qty: Number(p.qty),
          ...common,
          ...(single ? own : {}),
        }));
        return { detail: await createLines(orgId, purchaseId, lines), count: lines.length };
      }
      const body = {
        ...(draft.mode === "item" && draft.choice !== null ? refOf(draft.choice) : { item_id: null }),
        temp_name: draft.mode === "new" ? text(draft.tempName) : null,
        url: draft.mode === "new" ? text(draft.url) : null,
        image_url: draft.mode === "new" ? text(draft.imageUrl) : null,
        ordered_qty: Number(draft.ordered),
        ...own,
        ...common,
      };
      const detail = line ? await updateLine(orgId, purchaseId, line.id, body) : await createLine(orgId, purchaseId, body);
      return { detail, count: 1 };
    },
    onSuccess: ({ detail, count }) => onSaved(detail, count),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const title = editing ? t("purchases.lines.editTitle") : t("purchases.lines.addTitle");
  const submitLabel = many && draft.picked.length > 1 ? t("purchases.lines.addMany", { count: draft.picked.length }) : t("purchases.save");
  return (
    <Dialog
      open
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="line-form" disabled={!valid} loading={save.isPending}>
            {submitLabel}
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
        {draft.mode === "item" && (
          <>
            {picker.isError && <Banner tone="negative" title={errorText(picker.error, t)} />}
            {picker.isPending && <p className="caption">{t("purchases.lines.pickerLoading")}</p>}
            {picker.data && rows.length === 0 && <Banner tone="info" title={t("purchases.lines.pickerEmpty")} />}
            {picker.data?.truncated && <Banner tone="warning" title={t("purchases.lines.pickerTruncated")} />}
            {many ? (
              <>
                <Combobox
                  label={draft.picked.length === 0 ? t("purchases.lines.item") : t("purchases.lines.pickMore")}
                  placeholder={t("purchases.lines.pickItem")}
                  options={free}
                  value={null}
                  onValueChange={(key) => key && pick(key)}
                  limit={200}
                />
                {draft.picked.length === 0 ? (
                  <p className="caption">{t("purchases.lines.pickedEmpty")}</p>
                ) : (
                  <ul className="purchase-form__picked" aria-label={t("purchases.lines.picked")}>
                    {draft.picked.map((p) => (
                      <li key={p.key}>
                        <span className="purchase-form__picked-name">
                          {p.label}
                          {line === null && rowOf.get(p.key)?.item_id && taken.has(rowOf.get(p.key)!.item_id!) && <span className="caption"> · {t("purchases.lines.duplicate")}</span>}
                        </span>
                        <NumberInput label={t("purchases.lines.qty")} value={p.qty} onValueChange={(v) => setQty(p.key, v)} digits={0} />
                        <Button variant="ghost" onClick={() => patch({ picked: draft.picked.filter((x) => x.key !== p.key) })} aria-label={`${t("purchases.lines.remove")}: ${p.label}`}>
                          {t("purchases.lines.remove")}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <Combobox label={t("purchases.lines.item")} placeholder={t("purchases.lines.pickItem")} options={options} value={draft.choice} onValueChange={(choice) => patch({ choice })} limit={200} />
            )}
          </>
        )}
        {draft.mode === "new" && (
          <>
            <TextInput label={t("purchases.lines.tempName")} value={draft.tempName} onValueChange={(tempName) => patch({ tempName })} maxLength={200} />
            <TextInput label={t("purchases.lines.url")} optional type="url" value={draft.url} onValueChange={(url) => patch({ url })} maxLength={1000} />
            <TextInput label={t("purchases.lines.imageUrl")} optional type="url" value={draft.imageUrl} onValueChange={(imageUrl) => patch({ imageUrl })} maxLength={1000} />
          </>
        )}
        {single && <TextInput label={t("purchases.lines.variant")} optional value={draft.variant} onValueChange={(variant) => patch({ variant })} maxLength={200} />}
        {(!many || single) && (
          <div className="purchase-form__row">
            {!many && <NumberInput label={t("purchases.lines.orderedQty")} value={draft.ordered} onValueChange={(v) => patch({ ordered: v })} digits={0} />}
            {single && <NumberInput label={t("purchases.lines.receivedQty")} optional help={t("purchases.lines.receivedHint")} value={draft.received} onValueChange={(v) => patch({ received: v })} digits={0} />}
          </div>
        )}
        {many && draft.picked.length > 1 && <p className="caption">{t("purchases.lines.sharedHint")}</p>}
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
