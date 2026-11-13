// Kargo puli jadvali (TM3, ADR-061 §3, 04 §7.4 (2)): hamma "Yo'lda" xaridlar, kargo puli hali kiritilmaganlari. Har
// kartochkada summa (trekli — xaridning o'z kargo puli) va kg (ixtiyoriy, faqat ma'lumot); bir nechtasi belgilansa
// "Bitta qutiga birlashtirish" paneli: kod va umumiy summa → ulushlar dona bo'yicha (server, F20) inputlarda tayyor
// turadi, istalgani o'zgartiriladi, qoldiq ko'rinadi. Valyuta standarti USD; kurs — Markaziy bank yoki o'zim kiritaman.
// Tariflar kiritilmaydi — faqat yakuniy summa. Kartochkalar 360 px da ham, 1440 da ham bir xil.
import { keepPreviousData, useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { cargoPoolQuery, currentOrg, meQuery, previewBoxShares, saveCargoBox, saveTrackedCargo } from "../../app/query";
import { Banner, Button, EmptyState, MoneyInput, NumberInput, Segmented, Skeleton, TextInput, useToast } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { CargoPoolRow } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { PAID_CURRENCIES, type PaidCurrency } from "../purchases/model";
import { MANAGE_ROLES } from "../purchases/Purchases";

type RateMode = "cbu" | "manual";
type Row = { amount: string | null; kg: string | null };

const positive = (v: string | null | undefined) => v !== null && v !== undefined && v !== "" && Number(v) > 0;

/** Qutidagi qoldiq: umumiy summa − ko'rsatilgan ulushlar (faqat ko'rsatish uchun; tekshiruv serverda). */
export function boxRest(amount: string | null, shares: ReadonlyArray<string | null | undefined>): number | null {
  if (!positive(amount)) return null;
  const sum = shares.reduce((acc: number, s) => acc + (s === null || s === undefined || s === "" ? 0 : Number(s)), 0);
  return Math.round((Number(amount) - sum) * 100) / 100;
}

export function CargoPool() {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const [counted, setCounted] = useState(false);
  const pool = useQuery({ ...cargoPoolQuery(org.id, counted), placeholderData: keepPreviousData });
  const amounts = pool.data?.amounts ?? true;
  const canEdit = MANAGE_ROLES.includes(org.role) && amounts;
  const [currency, setCurrency] = useState<PaidCurrency>("USD");
  const [rateMode, setRateMode] = useState<RateMode>("cbu");
  const [rate, setRate] = useState<string | null>(null);
  const [paidOn, setPaidOn] = useState(todayTashkent());
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [picked, setPicked] = useState<string[]>([]);
  const [box, setBox] = useState<{ title: string; amount: string | null; kg: string | null }>({ title: "", amount: null, kg: null });
  const [fixed, setFixed] = useState<Record<string, string | null>>({});
  const items = useMemo(() => pool.data?.items ?? [], [pool.data]);
  const needsRate = currency !== "UZS" && rateMode === "manual";
  const rateOk = !needsRate || positive(rate);
  const row = (id: string): Row => rows[id] ?? { amount: null, kg: null };
  const setRow = (id: string, x: Partial<Row>) => setRows((r) => ({ ...r, [id]: { ...row(id), ...x } }));
  const boxing = picked.length > 0;
  const tracked = items.filter((x) => !picked.includes(x.purchase_id) && positive(row(x.purchase_id).amount));
  const fixedClean = Object.fromEntries(Object.entries(fixed).filter(([id, v]) => picked.includes(id) && v !== null && v !== "")) as Record<string, string>;
  const preview = useQuery({
    queryKey: ["orgs", org.id, "purchases", "cargo-pool", "shares", box.amount, currency, picked, fixedClean],
    queryFn: () => previewBoxShares(org.id, { amount: box.amount!, currency, purchase_ids: picked, fixed: fixedClean }),
    enabled: canEdit && boxing && positive(box.amount),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const shareOf = (id: string) => (fixed[id] !== undefined && fixed[id] !== null ? fixed[id] : (preview.data?.shares[id] ?? null));
  const rest = boxRest(
    box.amount,
    picked.map((id) => shareOf(id)),
  );
  const money = { currency, rate_mode: currency === "UZS" ? "cbu" : rateMode, ...(needsRate ? { rate } : {}), paid_on: paidOn || null };
  const done = async (message: string) => {
    await Promise.all([["purchases"], ["shipments"], ["inventory"], ["pnl"], ["dashboard"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", org.id, ...k] })));
    toast.show(message, "positive");
  };
  const saveTracked = useMutation({
    mutationFn: () =>
      saveTrackedCargo(org.id, {
        ...money,
        rows: tracked.map((x) => ({ purchase_id: x.purchase_id, amount: row(x.purchase_id).amount!, ...(positive(row(x.purchase_id).kg) ? { weight_kg: row(x.purchase_id).kg } : {}) })),
      }),
    onSuccess: async (out) => {
      setRows({});
      await done(t("cargo.trackedSaved", { count: out.created }));
    },
  });
  const saveBox = useMutation({
    mutationFn: () =>
      saveCargoBox(org.id, {
        ...money,
        title: box.title.trim(),
        amount: box.amount!,
        ...(positive(box.kg) ? { weight_kg: box.kg } : {}),
        purchase_ids: picked,
        fixed: fixedClean,
      }),
    onSuccess: async (out) => {
      setPicked([]);
      setFixed({});
      setBox({ title: "", amount: null, kg: null });
      await done(t("cargo.boxSaved"));
      void navigate({ to: "/shipments/$shipmentId", params: { shipmentId: out.shipment_id } });
    },
  });
  const boxValid = boxing && box.title.trim() !== "" && positive(box.amount) && rateOk && !preview.isError && rest === 0;
  const toggle = (id: string, on: boolean) => {
    setPicked((p) => (on ? [...p, id] : p.filter((x) => x !== id)));
    if (!on) setFixed((x) => Object.fromEntries(Object.entries(x).filter(([k]) => k !== id)));
  };
  const units = (r: CargoPoolRow) => t("cargo.units", { count: r.units });

  return (
    <section className="purchases cargo-pool">
      <Link to="/purchases" className="purchase__back">
        ← {t("shipments.backToPurchases")}
      </Link>
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("cargo.title")}</h1>
        </div>
        <span className="purchases__actions">
          <Link to="/shipments" className="ui-btn ui-btn--secondary ui-btn--md">
            {t("shipments.title")}
          </Link>
        </span>
      </header>
      <p className="caption">{t("cargo.lead")}</p>
      {!amounts && <Banner tone="info" title={t("purchases.noAmounts")}>{t("purchases.noAmountsText")}</Banner>}
      {canEdit && (
        <div className="cargo-pool__money" role="group" aria-label={t("cargo.moneyLabel")}>
          <Segmented label={t("purchases.quick.currency")} value={currency} onChange={setCurrency} options={PAID_CURRENCIES.map((c) => ({ value: c, label: c }))} />
          {currency !== "UZS" && (
            <Segmented
              label={t("purchases.quick.rate")}
              value={rateMode}
              onChange={setRateMode}
              options={[
                { value: "cbu", label: t("purchases.quick.rateCbu") },
                { value: "manual", label: t("purchases.quick.rateManual") },
              ]}
            />
          )}
          {needsRate && <NumberInput label={t("purchases.quick.rateValue", { currency })} value={rate} onValueChange={setRate} />}
          <TextInput label={t("cargo.paidOn")} type="date" value={paidOn} onValueChange={setPaidOn} />
        </div>
      )}
      <label className="quick-purchase__check cargo-pool__counted">
        <input type="checkbox" checked={counted} onChange={(e) => setCounted(e.target.checked)} /> <span>{t("cargo.showCounted")}</span>
      </label>
      {canEdit && boxing && (
        <div className="cargo-pool__box" role="region" aria-label={t("cargo.boxTitle")}>
          <h2 className="h3">{t("cargo.boxTitle")}</h2>
          <p className="caption">{t("cargo.boxHint", { count: picked.length })}</p>
          <div className="purchase-form__row">
            <TextInput label={t("cargo.boxCode")} help={t("cargo.boxCodeHint")} value={box.title} onValueChange={(title) => setBox((b) => ({ ...b, title }))} maxLength={300} />
            <MoneyInput label={t("cargo.boxAmount")} currency={currency} value={box.amount} onValueChange={(amount) => setBox((b) => ({ ...b, amount }))} />
            <NumberInput label={t("cargo.kg")} optional value={box.kg} onValueChange={(kg) => setBox((b) => ({ ...b, kg }))} suffix="kg" />
          </div>
          {preview.isError && <Banner tone="negative" title={errorText(preview.error, t)} />}
          {rest !== null && rest !== 0 && !preview.isError && <Banner tone="warning" title={t("cargo.boxRest", { rest: f.number(rest) })} />}
          {Object.keys(fixedClean).length > 0 && (
            <Button variant="ghost" onClick={() => setFixed({})}>
              {t("cargo.resetShares")}
            </Button>
          )}
          {saveBox.isError && <Banner tone="negative" title={errorText(saveBox.error, t)} />}
          <div className="cargo-pool__box-actions">
            <Button
              variant="ghost"
              onClick={() => {
                setPicked([]);
                setFixed({});
              }}
            >
              {t("cargo.boxCancel")}
            </Button>
            <Button variant="primary" disabled={!boxValid} loading={saveBox.isPending} onClick={() => saveBox.mutate()}>
              {t("cargo.boxSave")}
            </Button>
          </div>
        </div>
      )}
      {pool.isError ? (
        <Banner tone="negative" title={errorText(pool.error, t)} action={<Button onClick={() => void pool.refetch()}>{t("common.retry")}</Button>} />
      ) : !pool.data ? (
        <Skeleton label={t("common.loading")} lines={5} />
      ) : items.length === 0 ? (
        <EmptyState title={t("cargo.empty")} text={t("cargo.emptyText")} />
      ) : (
        <ul className="cargo-pool__list" aria-label={t("cargo.list")}>
          {items.map((r) => {
            const inBox = picked.includes(r.purchase_id);
            const name = r.title || r.items.join(", ") || t("purchases.untitled");
            return (
              <li key={r.purchase_id} className={cx("cargo-pool__card", inBox && "is-picked")}>
                <div className="cargo-pool__head">
                  {canEdit && (
                    <label className="cargo-pool__pick">
                      <input type="checkbox" checked={inBox} onChange={(e) => toggle(r.purchase_id, e.target.checked)} aria-label={t("cargo.pick", { name })} />
                    </label>
                  )}
                  <span className="purchase-cell">
                    <Link to="/purchases/$purchaseId" params={{ purchaseId: r.purchase_id }} className="purchase-cell__title">
                      {name}
                    </Link>
                    <span className="caption">
                      {[r.title ? r.items.join(", ") : null, units(r), r.track_no ? t("purchases.trackShort", { track: r.track_no }) : null, r.supplier_name, r.ordered_on ? f.date(r.ordered_on) : null, r.state === "in_stock" ? t("purchases.state.in_stock") : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </div>
                {canEdit &&
                  (inBox ? (
                    <div className="cargo-pool__inputs">
                      <MoneyInput label={t("cargo.share")} aria-label={t("cargo.shareOf", { name })} currency={currency} value={shareOf(r.purchase_id)} onValueChange={(v) => setFixed((x) => ({ ...x, [r.purchase_id]: v }))} />
                    </div>
                  ) : (
                    <div className="cargo-pool__inputs">
                      <MoneyInput label={t("cargo.amount")} aria-label={t("cargo.amountOf", { name })} optional currency={currency} value={row(r.purchase_id).amount} onValueChange={(amount) => setRow(r.purchase_id, { amount })} />
                      <NumberInput label={t("cargo.kg")} aria-label={t("cargo.kgOf", { name })} optional value={row(r.purchase_id).kg} onValueChange={(kg) => setRow(r.purchase_id, { kg })} suffix="kg" />
                    </div>
                  ))}
              </li>
            );
          })}
        </ul>
      )}
      {canEdit && items.length > 0 && (
        <div className="cargo-pool__footer">
          {saveTracked.isError && <Banner tone="negative" title={errorText(saveTracked.error, t)} />}
          <p className="caption">{t("cargo.trackedHint")}</p>
          <Button variant="primary" disabled={tracked.length === 0 || !rateOk} loading={saveTracked.isPending} onClick={() => saveTracked.mutate()}>
            {t("cargo.trackedSave", { count: tracked.length })}
          </Button>
        </div>
      )}
    </section>
  );
}
