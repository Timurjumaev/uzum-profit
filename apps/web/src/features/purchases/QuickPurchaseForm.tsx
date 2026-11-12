// Yangi xarid — bitta qisqa oyna (ADR-061 §2, 04 §7.4): tovarlar (SKU, dona), jami to'landi + valyuta (CNY / USD / UZS —
// hisobdan real yechilgan summa), kurs (o'sha kungi Markaziy bank kursi yoki sotuvchi o'zi kiritadi), trek raqami
// (ixtiyoriy). Bir buyurtmada har xil tovar bo'lsa — har qatorga qator summasi (1688'dagi qator jami, dona narxi emas);
// jami bilan farq (ichki yetkazish, komissiya) qator summasiga mutanosib bo'linadi — hisob serverda (F20). Saqlanganda
// darhol "Yo'lda"; "Tovar qo'limda" (mahalliy xarid) — darhol "Omborimda". Omborchi summalarni kiritmaydi.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createQuickPurchase, skuPickerQuery } from "../../app/query";
import { Banner, Button, Combobox, Dialog, MoneyInput, NumberInput, Segmented, TextInput, useToast } from "../../components/ui";
import type { PickerRow, PurchaseDetail, QuickPurchaseIn } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { PAID_CURRENCIES, pickerKey, pickerLabel, pickerOptions, type PaidCurrency } from "./model";

type Picked = { key: string; label: string; qty: string | null; sum: string | null };
type RateMode = "cbu" | "manual";
type Draft = {
  picked: Picked[];
  newName: string;
  paid: string | null;
  currency: PaidCurrency;
  rateMode: RateMode;
  rate: string | null;
  orderedOn: string;
  trackNo: string;
  onHand: boolean;
  note: string;
};

const NEW_PREFIX = "new:";
const whole = (v: string | null) => v !== null && v !== "" && Number.isInteger(Number(v)) && Number(v) >= 1;
const positive = (v: string | null) => v !== null && v !== "" && Number(v) > 0;

/** Qator summalari yig'indisi jamidan oshmasligi kerak (API ham tekshiradi) — shaklda oldindan aytish uchun. */
export function sumsExceed(paid: string | null, sums: ReadonlyArray<string | null>): boolean {
  if (!positive(paid)) return false;
  const total = sums.reduce((acc, s) => acc + (s === null || s === "" ? 0 : Number(s)), 0);
  return total > Number(paid) + 1e-9;
}

export function QuickPurchaseForm({ orgId, amounts, onClose, onSaved }: { orgId: string; amounts: boolean; onClose: () => void; onSaved: (detail: PurchaseDetail) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const picker = useQuery(skuPickerQuery(orgId));
  const [draft, setDraft] = useState<Draft>({
    picked: [],
    newName: "",
    paid: null,
    currency: "CNY",
    rateMode: "cbu",
    rate: null,
    orderedOn: todayTashkent(),
    trackNo: "",
    onHand: false,
    note: "",
  });
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const rows = useMemo(() => picker.data?.rows ?? [], [picker.data]);
  const rowOf = useMemo(() => new Map<string, PickerRow>(rows.map((r) => [pickerKey(r), r])), [rows]);
  const options = useMemo(() => pickerOptions(rows, t, new Set()).filter((o) => !draft.picked.some((p) => p.key === o.value)), [rows, t, draft.picked]);
  const pick = (key: string) => {
    const row = rowOf.get(key);
    if (!row || draft.picked.some((p) => p.key === key)) return;
    const variant = row.title && row.title !== pickerLabel(row) ? ` · ${row.title}` : "";
    patch({ picked: [...draft.picked, { key, label: `${pickerLabel(row)}${variant}`, qty: null, sum: null }] });
  };
  const addNew = () => {
    const name = draft.newName.trim();
    if (name === "") return;
    patch({ picked: [...draft.picked, { key: `${NEW_PREFIX}${draft.picked.length}:${name}`, label: name, qty: null, sum: null }], newName: "" });
  };
  const setLine = (key: string, x: Partial<Picked>) => patch({ picked: draft.picked.map((p) => (p.key === key ? { ...p, ...x } : p)) });
  const several = draft.picked.length > 1;
  const needsRate = amounts && draft.currency !== "UZS" && draft.rateMode === "manual";
  const exceed = amounts && several && sumsExceed(draft.paid, draft.picked.map((p) => p.sum));
  const valid =
    draft.picked.length > 0 &&
    draft.picked.every((p) => whole(p.qty)) &&
    (!amounts || draft.paid === null || draft.paid === "" || positive(draft.paid)) &&
    (!needsRate || draft.paid === null || draft.paid === "" || positive(draft.rate)) &&
    !exceed;
  const save = useMutation({
    mutationFn: () => {
      const paid = amounts && positive(draft.paid) ? draft.paid : null;
      const body: QuickPurchaseIn = {
        lines: draft.picked.map((p) => ({
          ...(p.key.startsWith("sku:") ? { sku_id: p.key.slice(4) } : p.key.startsWith("item:") ? { item_id: p.key.slice(5) } : { temp_name: p.label }),
          qty: Number(p.qty),
          ...(amounts && several && positive(p.sum) ? { line_sum: p.sum } : {}),
        })),
        ...(paid !== null
          ? {
              paid_amount: paid,
              currency: draft.currency,
              rate_mode: draft.currency === "UZS" ? "cbu" : draft.rateMode,
              ...(needsRate ? { rate: draft.rate } : {}),
            }
          : {}),
        ordered_on: draft.orderedOn || null,
        track_no: draft.trackNo.trim() || null,
        note: draft.note.trim() || null,
        on_hand: draft.onHand,
      };
      return createQuickPurchase(orgId, body);
    },
    onSuccess: async (saved) => {
      await Promise.all([["purchases"], ["inventory"], ["pnl"], ["dashboard"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
      toast.show(t("purchases.created"), "positive");
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
      title={t("purchases.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="quick-purchase-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.save")}
          </Button>
        </>
      }
    >
      <form id="quick-purchase-form" className="purchase-form quick-purchase" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        {picker.isError && <Banner tone="negative" title={errorText(picker.error, t)} />}
        {picker.data?.truncated && <Banner tone="warning" title={t("purchases.lines.pickerTruncated")} />}
        <Combobox
          label={draft.picked.length === 0 ? t("purchases.quick.items") : t("purchases.lines.pickMore")}
          help={picker.isPending ? t("purchases.lines.pickerLoading") : undefined}
          placeholder={t("purchases.lines.pickItem")}
          options={options}
          value={null}
          onValueChange={(key) => key && pick(key)}
          limit={200}
        />
        <div className="quick-purchase__new">
          <TextInput label={t("purchases.quick.newItem")} help={t("purchases.quick.newItemHint")} optional value={draft.newName} onValueChange={(newName) => patch({ newName })} maxLength={200} />
          <Button variant="secondary" onClick={addNew} disabled={draft.newName.trim() === ""}>
            {t("purchases.quick.addNew")}
          </Button>
        </div>
        {draft.picked.length === 0 ? (
          <p className="caption">{t("purchases.lines.pickedEmpty")}</p>
        ) : (
          <ul className="purchase-form__picked" aria-label={t("purchases.lines.picked")}>
            {draft.picked.map((p) => (
              <li key={p.key} className={amounts && several ? "has-sum" : undefined}>
                <span className="purchase-form__picked-name">{p.label}</span>
                <NumberInput label={t("purchases.lines.qty")} value={p.qty} onValueChange={(qty) => setLine(p.key, { qty })} digits={0} />
                {amounts && several && <MoneyInput label={t("purchases.quick.lineSum")} optional currency={draft.currency} value={p.sum} onValueChange={(sum) => setLine(p.key, { sum })} />}
                <Button variant="ghost" onClick={() => patch({ picked: draft.picked.filter((x) => x.key !== p.key) })} aria-label={`${t("purchases.lines.remove")}: ${p.label}`}>
                  {t("purchases.lines.remove")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {amounts && several && <p className="caption">{t("purchases.quick.lineSumHint")}</p>}
        {exceed && <Banner tone="negative" title={t("purchases.quick.sumsExceed")} />}
        {amounts && (
          <>
            <div className="purchase-form__row">
              <MoneyInput label={t("purchases.quick.paid")} help={t("purchases.quick.paidHint")} optional currency={draft.currency} value={draft.paid} onValueChange={(paid) => patch({ paid })} />
              <Segmented label={t("purchases.quick.currency")} value={draft.currency} onChange={(currency) => patch({ currency })} options={PAID_CURRENCIES.map((c) => ({ value: c, label: c }))} />
            </div>
            {draft.currency !== "UZS" && (
              <div className="purchase-form__row">
                <Segmented
                  label={t("purchases.quick.rate")}
                  value={draft.rateMode}
                  onChange={(rateMode) => patch({ rateMode })}
                  options={[
                    { value: "cbu", label: t("purchases.quick.rateCbu") },
                    { value: "manual", label: t("purchases.quick.rateManual") },
                  ]}
                />
                {draft.rateMode === "manual" && <NumberInput label={t("purchases.quick.rateValue", { currency: draft.currency })} value={draft.rate} onValueChange={(rate) => patch({ rate })} />}
              </div>
            )}
          </>
        )}
        <div className="purchase-form__row">
          <TextInput label={t("purchases.fields.orderedOn")} type="date" value={draft.orderedOn} onValueChange={(orderedOn) => patch({ orderedOn })} />
          <TextInput label={t("purchases.quick.track")} optional value={draft.trackNo} onValueChange={(trackNo) => patch({ trackNo })} maxLength={100} />
        </div>
        <label className="quick-purchase__check">
          <input type="checkbox" checked={draft.onHand} onChange={(e) => patch({ onHand: e.target.checked })} /> <span>{t("purchases.quick.onHand")}</span>
          <span className="caption">{t("purchases.quick.onHandHint")}</span>
        </label>
        <TextInput label={t("purchases.fields.note")} optional value={draft.note} onValueChange={(note) => patch({ note })} maxLength={500} />
      </form>
    </Dialog>
  );
}
