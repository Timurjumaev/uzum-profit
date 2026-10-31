// Xarajat komponenti shakli (M9): tur, summa + valyuta, to'lov sanasi, kurs rejimi (CBU — to'lov sanasi bo'yicha;
// qo'lda; "kartadan yechilgan summa" — effektiv kurs serverda), taqsimot asosi (bo'sh — tur standarti, serverda),
// tegishli qatorlar va qo'lda ulushlar. Kurs va so'mdagi summa shu yerda hisoblanmaydi — saqlangach API'dan.
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createComponent, updateComponent } from "../../app/query";
import { Banner, Button, Dialog, MoneyInput, NumberInput, Select, TextInput } from "../../components/ui";
import type { AllocationBase, ComponentKind, CostComponent, PurchaseDetail, PurchaseLine } from "../../lib/api/types";
import { ALLOCATIONS, COMPONENT_KINDS, CURRENCIES, type CurrencyCode } from "./model";

type RateMode = "cbu" | "manual" | "effective";
type Draft = {
  kind: ComponentKind;
  amount: string | null;
  currency: CurrencyCode;
  paidOn: string;
  rateMode: RateMode;
  rate: string | null;
  charged: string | null;
  chargedCurrency: CurrencyCode;
  allocation: AllocationBase | "";
  all: boolean;
  lines: string[];
  shares: Record<string, string | null>;
};

function draftOf(c: CostComponent | null, lines: PurchaseLine[]): Draft {
  return {
    kind: (c?.kind as ComponentKind | undefined) ?? "goods",
    amount: c?.amount ?? null,
    currency: (c?.currency as CurrencyCode | undefined) ?? "CNY",
    paidOn: c?.paid_on ?? "",
    rateMode: (c?.rate_mode as RateMode | undefined) ?? "cbu",
    rate: c?.rate ?? null,
    charged: c?.charged_amount ?? null,
    chargedCurrency: (c?.charged_currency as CurrencyCode | null) ?? "USD",
    allocation: (c?.allocation as AllocationBase | undefined) ?? "",
    all: !c?.lines,
    lines: c?.lines ?? lines.map((l) => l.id),
    shares: Object.fromEntries(lines.map((l) => [l.id, c?.shares[l.id] ?? null])),
  };
}

export const lineLabel = (l: PurchaseLine) => [l.item_name ?? l.temp_name ?? "—", l.variant].filter(Boolean).join(" · ");

type Props = { orgId: string; purchaseId: string; component: CostComponent | null; lines: PurchaseLine[]; onClose: () => void; onSaved: (d: PurchaseDetail) => void };

export function ComponentForm({ orgId, purchaseId, component, lines, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(() => draftOf(component, lines));
  const patch = (x: Partial<Draft>) => setDraft((d) => ({ ...d, ...x }));
  const foreign = draft.currency !== "UZS";
  const targets = draft.all ? lines.map((l) => l.id) : draft.lines;
  const valid =
    draft.amount !== null &&
    Number(draft.amount) > 0 &&
    (!foreign || draft.rateMode !== "manual" || (draft.rate !== null && Number(draft.rate) > 0)) &&
    (!foreign || draft.rateMode !== "effective" || (draft.charged !== null && Number(draft.charged) > 0 && draft.chargedCurrency !== draft.currency)) &&
    targets.length > 0 &&
    (draft.allocation !== "manual" || targets.every((id) => draft.shares[id] !== null));
  const save = useMutation({
    mutationFn: () => {
      const rateMode = foreign ? draft.rateMode : "cbu";
      const body = {
        kind: draft.kind,
        amount: draft.amount!,
        currency: draft.currency,
        paid_on: draft.paidOn || null,
        rate_mode: rateMode,
        rate: rateMode === "manual" ? draft.rate : null,
        charged_amount: rateMode === "effective" ? draft.charged : null,
        charged_currency: rateMode === "effective" ? draft.chargedCurrency : null,
        allocation: draft.allocation === "" ? null : draft.allocation,
        lines: draft.all ? null : draft.lines,
        shares: draft.allocation === "manual" ? Object.fromEntries(targets.map((id) => [id, draft.shares[id]!])) : {},
      };
      return component ? updateComponent(orgId, purchaseId, component.id, body) : createComponent(orgId, purchaseId, body);
    },
    onSuccess: onSaved,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const toggle = (id: string, on: boolean) => patch({ lines: on ? [...draft.lines, id] : draft.lines.filter((x) => x !== id) });
  const currencyOptions = CURRENCIES.map((c) => ({ value: c, label: c }));
  return (
    <Dialog
      open
      title={component ? t("purchases.components.editTitle") : t("purchases.components.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="component-form" disabled={!valid} loading={save.isPending}>
            {t("purchases.save")}
          </Button>
        </>
      }
    >
      <form id="component-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <Select
          label={t("purchases.components.col.kind")}
          value={draft.kind}
          onValueChange={(kind) => patch({ kind: kind as ComponentKind })}
          options={COMPONENT_KINDS.map((k) => ({ value: k, label: t(`purchases.components.kind.${k}`) }))}
        />
        <div className="purchase-form__row">
          <MoneyInput label={t("purchases.components.amount")} currency={draft.currency} value={draft.amount} onValueChange={(amount) => patch({ amount })} />
          <Select label={t("purchases.components.currency")} value={draft.currency} onValueChange={(c) => patch({ currency: c as CurrencyCode })} options={currencyOptions} />
        </div>
        <TextInput label={t("purchases.components.paidOn")} help={t("purchases.components.paidOnHint")} optional type="date" value={draft.paidOn} onValueChange={(paidOn) => patch({ paidOn })} />
        {foreign && (
          <fieldset className="purchase-form__modes">
            <legend className="ui-field__label">{t("purchases.components.rateTitle")}</legend>
            {(["cbu", "manual", "effective"] as const).map((m) => (
              <label key={m}>
                <input type="radio" name="rate-mode" checked={draft.rateMode === m} onChange={() => patch({ rateMode: m })} /> {t(`purchases.components.rateMode.${m}`)}
              </label>
            ))}
          </fieldset>
        )}
        {foreign && draft.rateMode === "manual" && <NumberInput label={t("purchases.components.rate")} value={draft.rate} onValueChange={(rate) => patch({ rate })} />}
        {foreign && draft.rateMode === "effective" && (
          <div className="purchase-form__row">
            <MoneyInput label={t("purchases.components.charged")} help={t("purchases.components.chargedHint")} currency={draft.chargedCurrency} value={draft.charged} onValueChange={(charged) => patch({ charged })} />
            <Select label={t("purchases.components.chargedCurrency")} value={draft.chargedCurrency} onValueChange={(c) => patch({ chargedCurrency: c as CurrencyCode })} options={currencyOptions} />
          </div>
        )}
        <Select
          label={t("purchases.components.allocationLabel")}
          value={draft.allocation}
          onValueChange={(a) => patch({ allocation: a as AllocationBase | "" })}
          options={[{ value: "", label: t("purchases.components.allocation.default") }, ...ALLOCATIONS.map((a) => ({ value: a, label: t(`purchases.components.allocation.${a}`) }))]}
        />
        <fieldset className="purchase-form__lines">
          <legend className="ui-field__label">{t("purchases.components.targets")}</legend>
          <label>
            <input type="checkbox" checked={draft.all} onChange={(e) => patch({ all: e.target.checked })} /> {t("purchases.components.allLines")}
          </label>
          {!draft.all &&
            lines.map((l) => (
              <label key={l.id}>
                <input type="checkbox" checked={draft.lines.includes(l.id)} onChange={(e) => toggle(l.id, e.target.checked)} /> {lineLabel(l)}
              </label>
            ))}
        </fieldset>
        {draft.allocation === "manual" && (
          <div className="purchase-form__shares">
            <p className="caption">{t("purchases.components.sharesHint")}</p>
            {lines
              .filter((l) => targets.includes(l.id))
              .map((l) => (
                <NumberInput
                  key={l.id}
                  label={t("purchases.components.share", { name: lineLabel(l) })}
                  value={draft.shares[l.id] ?? null}
                  onValueChange={(v) => patch({ shares: { ...draft.shares, [l.id]: v } })}
                />
              ))}
          </div>
        )}
      </form>
    </Dialog>
  );
}
