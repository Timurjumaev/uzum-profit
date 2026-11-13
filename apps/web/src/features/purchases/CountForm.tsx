// Sanash oynasi (TM4, ADR-061 §6, 04 §7.4 (3)): har qatorda nom, buyurtma soni, "Kelgan" (− / + va raqam, 44 px) va
// "Brak"; tepada "Hammasi keldi". Kelgan son buyurtmadan kam bo'lsa "Sotuvchi qaytargan summa" maydoni ochiladi. Qadoq
// qo'shimchasi (so'm/dona) — qatorda, bo'sh qolsa tovardagi qiymat olinadi; "Tovarga eslab qolish". Hisob serverda (F20):
// saqlangach yangi birlik tannarx va brak narxi xarid sahifasida. Omborchi summalarni kiritmaydi.
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { countPurchase } from "../../app/query";
import { Banner, Button, Dialog, MoneyInput, NumberInput, Select, TextInput } from "../../components/ui";
import type { PurchaseDetail } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { lineLabel } from "./ComponentForm";
import { PAID_CURRENCIES, type PaidCurrency } from "./model";

type Row = { received: string | null; defect: string | null; pack: string | null };

const whole = (v: string | null) => v !== null && v !== "" && Number.isInteger(Number(v)) && Number(v) >= 0;

export function CountForm({ orgId, detail, onClose, onSaved }: { orgId: string; detail: PurchaseDetail; onClose: () => void; onSaved: (d: PurchaseDetail) => void }) {
  const { t } = useTranslation();
  const amounts = detail.amounts;
  const p = detail.purchase;
  // Boshqa SKU'ga o'tkazilgan qatorlar sanalmaydi (Omborimda boshqariladi).
  const lines = detail.lines.filter((l) => !l.source_line_id);
  const [rows, setRows] = useState<Record<string, Row>>(() =>
    Object.fromEntries(detail.lines.filter((l) => !l.source_line_id).map((l) => [l.id, { received: String(l.received_qty ?? l.ordered_qty), defect: String(l.defect_qty), pack: l.pack_unit_cost }])),
  );
  const [countedOn, setCountedOn] = useState(todayTashkent());
  const [refund, setRefund] = useState<string | null>(p.refund_amount);
  const [refundCurrency, setRefundCurrency] = useState<PaidCurrency>(((p.refund_currency as PaidCurrency | null) ?? "CNY") as PaidCurrency);
  const [remember, setRemember] = useState(false);
  const set = (id: string, x: Partial<Row>) => setRows((r) => ({ ...r, [id]: { ...r[id]!, ...x } }));
  const step = (id: string, by: number) => set(id, { received: String(Math.max(0, Number(rows[id]!.received ?? 0) + by)) });
  const short = lines.some((l) => whole(rows[l.id]!.received) && Number(rows[l.id]!.received) < l.ordered_qty);
  const valid = lines.every((l) => {
    const r = rows[l.id]!;
    return whole(r.received) && whole(r.defect ?? "0") && Number(r.defect ?? 0) <= Number(r.received);
  });
  const save = useMutation({
    mutationFn: () =>
      countPurchase(orgId, p.id, {
        counted_on: countedOn || null,
        remember_pack: amounts && remember,
        lines: lines.map((l) => {
          const r = rows[l.id]!;
          return {
            line_id: l.id,
            received_qty: Number(r.received),
            defect_qty: Number(r.defect ?? 0),
            ...(amounts && r.pack !== null && r.pack !== "" ? { pack_unit_cost: r.pack } : {}),
          };
        }),
        ...(amounts && refund !== null && refund !== "" ? { refund_amount: refund, refund_currency: refundCurrency } : {}),
      }),
    onSuccess: onSaved,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("purchases.count.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="count-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.count.save")}
          </Button>
        </>
      }
    >
      <form id="count-form" className="purchase-form count-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <p className="caption">{t("purchases.count.hint")}</p>
        <div className="purchase-form__row">
          <TextInput label={t("purchases.count.date")} type="date" value={countedOn} onValueChange={setCountedOn} />
          <Button variant="secondary" onClick={() => setRows((r) => Object.fromEntries(lines.map((l) => [l.id, { ...r[l.id]!, received: String(l.ordered_qty) }])))}>
            {t("purchases.count.all")}
          </Button>
        </div>
        <ul className="count-form__lines" aria-label={t("purchases.lines.title")}>
          {lines.map((l) => {
            const r = rows[l.id]!;
            const name = lineLabel(l);
            return (
              <li key={l.id}>
                <span className="count-form__name">
                  <strong>{name}</strong>
                  <span className="caption">{t("purchases.count.ordered", { count: l.ordered_qty })}</span>
                </span>
                <div className="count-form__qty">
                  <Button variant="secondary" onClick={() => step(l.id, -1)} aria-label={t("purchases.count.minus", { name })}>
                    −
                  </Button>
                  <NumberInput label={t("purchases.count.received")} aria-label={t("purchases.count.receivedOf", { name })} value={r.received} onValueChange={(received) => set(l.id, { received })} digits={0} />
                  <Button variant="secondary" onClick={() => step(l.id, 1)} aria-label={t("purchases.count.plus", { name })}>
                    +
                  </Button>
                </div>
                <NumberInput label={t("purchases.count.defect")} aria-label={t("purchases.count.defectOf", { name })} value={r.defect} onValueChange={(defect) => set(l.id, { defect })} digits={0} />
                {amounts && <MoneyInput label={t("purchases.count.pack")} aria-label={t("purchases.count.packOf", { name })} optional value={r.pack} onValueChange={(pack) => set(l.id, { pack })} />}
              </li>
            );
          })}
        </ul>
        {!valid && <Banner tone="warning" title={t("purchases.count.invalid")} />}
        {amounts && (
          <label className="quick-purchase__check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> <span>{t("purchases.count.remember")}</span>
          </label>
        )}
        {amounts && (short || p.refund_amount !== null) && (
          <div className="purchase-form__row">
            <MoneyInput label={t("purchases.count.refund")} help={t("purchases.count.refundHint")} optional currency={refundCurrency} value={refund} onValueChange={setRefund} />
            <Select label={t("purchases.quick.currency")} value={refundCurrency} onValueChange={(c) => setRefundCurrency(c as PaidCurrency)} options={PAID_CURRENCIES.map((c) => ({ value: c, label: c }))} />
          </div>
        )}
      </form>
    </Dialog>
  );
}
