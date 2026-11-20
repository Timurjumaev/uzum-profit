// Kalkulyator (M13, B5.9; F35–F37): xariddan oldin — 1688 narxi, Xitoy ichki yetkazish, kargo ($/kg yoki $/m³), o'lcham,
// komissiya, soliq va mo'ljallangan narxdan birlik tannarx, Uzum logistikasi, foyda, marja, ROI, zararsizlik va maqsadli
// marja narxi. Hisob serverda (`/calculator`, tamoyil 4) — bu yerda faqat kiritish va ko'rsatish. Kurs — CBU (manbasi va sanasi
// ko'rsatiladi), qo'lda o'zgartirsa bo'ladi; qiymat yo'q bo'lsa taxmin qilinmaydi: maydon bo'sh.
import { keepPreviousData, useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { calculatorDefaultsQuery, cargoSuggestionQuery, deleteScenario, saveScenario, scenariosQuery, calculatorQuery, currentOrg, meQuery, type CalculatorInput } from "../../app/query";
import { errorText } from "../../app/errors";
import { Banner, Button, FormulaPopover, NumberInput, Skeleton, TextInput, useToast } from "../../components/ui";
import { ApiError } from "../../lib/api/client";
import type { CalculatorDefaults } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

export type Field =
  | "price_cny"
  | "qty"
  | "china_cny_total"
  | "weight_kg"
  | "length_cm"
  | "width_cm"
  | "height_cm"
  | "cargo_usd_per_kg"
  | "cargo_usd_per_m3"
  | "extra_uzs"
  | "packaging_uzs"
  | "price"
  | "commission_pct"
  | "tax_pct"
  | "ads_pct"
  | "target_margin_pct"
  | "cny_rate"
  | "usd_rate";
export type Values = Record<Field, string | null>;

const DEBOUNCE_MS = 300;
const EMPTY: Values = {
  price_cny: null,
  qty: "100",
  china_cny_total: null,
  weight_kg: null,
  length_cm: null,
  width_cm: null,
  height_cm: null,
  cargo_usd_per_kg: null,
  cargo_usd_per_m3: null,
  extra_uzs: null,
  packaging_uzs: null,
  price: null,
  commission_pct: null,
  tax_pct: null,
  ads_pct: null,
  target_margin_pct: null,
  cny_rate: null,
  usd_rate: null,
};

/** Hisob uchun kiritish: majburiy maydonlar (1688 narxi, sotuv narxi, komissiya, dona) bo'lmasa `null`; bo'sh ixtiyoriy maydon yuborilmaydi
 * (server taklifi / 0 ishlatadi). O'lcham — uchalasi birga bo'lsagina yuboriladi. */
export function toInput(v: Values): CalculatorInput | null {
  if (v.price_cny === null || v.price === null || v.commission_pct === null || v.qty === null || Number(v.qty) < 1) return null;
  const dims = v.length_cm !== null && v.width_cm !== null && v.height_cm !== null;
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(v)) {
    if (value === null) continue;
    if ((key === "length_cm" || key === "width_cm" || key === "height_cm") && !dims) continue;
    out[key] = value;
  }
  return out as unknown as CalculatorInput;
}

/** Ssenariyga faqat to'ldirilgan maydonlar saqlanadi (bo'sh — server taklifi / 0). */
export function scenarioInputs(v: Values): Record<string, string> {
  return Object.fromEntries(Object.entries(v).filter((e): e is [string, string] => e[1] !== null));
}

/** Saqlangan kiritishni formaga qaytarish: noma'lum maydon e'tiborga olinmaydi, qolganlari bo'sh. */
export function fromScenario(inputs: Record<string, string>): Values {
  const out: Values = { ...EMPTY };
  for (const key of Object.keys(EMPTY) as Field[]) out[key] = inputs[key] ?? null;
  return out;
}

function useDebounced<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setOut(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return out;
}

export function CalculatorPage() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const defaults = useQuery(calculatorDefaultsQuery(org.id));
  return (
    <section className="calculator">
      <header className="page-title">
        <h1 className="h2">{t("calculator.title")}</h1>
      </header>
      <p className="caption">{t("calculator.lead")}</p>
      {defaults.isError ? (
        <Banner tone="negative" title={errorText(defaults.error, t)} action={<Button onClick={() => void defaults.refetch()}>{t("common.retry")}</Button>} />
      ) : !defaults.data ? (
        <Skeleton label={t("common.loading")} lines={8} />
      ) : (
        <Form orgId={org.id} defaults={defaults.data} />
      )}
    </section>
  );
}

function Form({ orgId, defaults }: { orgId: string; defaults: CalculatorDefaults }) {
  const { t } = useTranslation();
  const f = useFormat();
  const start = useMemo<Values>(() => ({ ...EMPTY, tax_pct: defaults.tax_pct }), [defaults.tax_pct]);
  const [values, setValues] = useState<Values>(start);
  const set = (field: Field) => (value: string | null) => setValues((v) => ({ ...v, [field]: value }));
  const [scenarioName, setScenarioName] = useState("");
  const toast = useToast();
  const qc = useQueryClient();
  const scenarios = useQuery(scenariosQuery(orgId)).data ?? [];
  const refresh = () => void qc.invalidateQueries({ queryKey: ["orgs", orgId, "calculator-scenarios"] });
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const save = useMutation({
    mutationFn: () => saveScenario(orgId, scenarioName.trim(), scenarioInputs(values)),
    onSuccess: () => {
      toast.show(t("calculator.scenario.saved"), "positive");
      refresh();
    },
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (id: string) => deleteScenario(orgId, id), onSuccess: refresh, onError: fail });
  const suggestion = useQuery(cargoSuggestionQuery(orgId)).data;
  const key = useDebounced(JSON.stringify(toInput(values)), DEBOUNCE_MS);
  const input = useMemo(() => JSON.parse(key) as CalculatorInput | null, [key]);
  const result = useQuery({ ...calculatorQuery(orgId, input!), enabled: input !== null, placeholderData: keepPreviousData });
  const c = input === null || result.isError ? undefined : result.data;
  const failure = result.isError
    ? result.error instanceof ApiError && result.error.status === 422
      ? t(result.error.code === "fx_rate_missing" ? "calculator.noRate" : "calculator.invalid")
      : errorText(result.error, t)
    : null;
  const help = (name: string, metric: string) => (
    <FormulaPopover metric={metric} code={t(`calculator.formula.${name}.code`)} formula={t(`calculator.formula.${name}.formula`)} source={t(`calculator.formula.${name}.source`)} />
  );
  const rate = defaults.rates;
  const rateHint = (value: string | null) =>
    value === null ? t("calculator.rateMissing") : t(`calculator.rateSource.${rate.source ?? "cbu"}`, { value: f.number(value, { digits: 2, trim: true }), day: rate.day ? f.date(rate.day) : "" });
  return (
    <div className="calculator__grid">
      <div className="calculator__inputs">
        <fieldset className="calculator__group">
          <legend className="h4">{t("calculator.group.goods")}</legend>
          <NumberInput label={t("calculator.price_cny")} value={values.price_cny} onValueChange={set("price_cny")} suffix="¥" />
          <NumberInput label={t("calculator.qty")} value={values.qty} onValueChange={set("qty")} digits={0} />
          <NumberInput label={t("calculator.china_cny_total")} value={values.china_cny_total} onValueChange={set("china_cny_total")} suffix="¥" optional help={t("calculator.china_cny_totalHelp")} />
        </fieldset>
        <fieldset className="calculator__group">
          <legend className="h4">{t("calculator.group.cargo")}</legend>
          <NumberInput label={t("calculator.weight_kg")} value={values.weight_kg} onValueChange={set("weight_kg")} suffix="kg" optional />
          <div className="calculator__dims">
            <NumberInput label={t("calculator.length_cm")} value={values.length_cm} onValueChange={set("length_cm")} suffix="sm" optional />
            <NumberInput label={t("calculator.width_cm")} value={values.width_cm} onValueChange={set("width_cm")} suffix="sm" optional />
            <NumberInput label={t("calculator.height_cm")} value={values.height_cm} onValueChange={set("height_cm")} suffix="sm" optional />
          </div>
          <p className="caption">{t("calculator.dimsHelp")}</p>
          <NumberInput label={t("calculator.cargo_usd_per_kg")} value={values.cargo_usd_per_kg} onValueChange={set("cargo_usd_per_kg")} suffix="$/kg" optional />
          <NumberInput label={t("calculator.cargo_usd_per_m3")} value={values.cargo_usd_per_m3} onValueChange={set("cargo_usd_per_m3")} suffix="$/m³" optional help={t("calculator.cargoHelp")} />
          {suggestion && suggestion.purchases > 0 && (suggestion.usd_per_kg !== null || suggestion.uzs_per_unit !== null) && (
            <div className="calculator__suggest" data-testid="cargo-suggestion">
              <p className="caption">
                {t("calculator.cargoSuggest", { count: suggestion.purchases })}{" "}
                {suggestion.usd_per_kg !== null && <strong>{t("calculator.cargoSuggestKg", { value: f.number(suggestion.usd_per_kg, { digits: 2, trim: true }) })}</strong>}
                {suggestion.usd_per_kg !== null && suggestion.uzs_per_unit !== null && " · "}
                {suggestion.uzs_per_unit !== null && t("calculator.cargoSuggestUnit", { value: f.money(suggestion.uzs_per_unit) })}
              </p>
              {suggestion.usd_per_kg !== null && values.cargo_usd_per_kg !== suggestion.usd_per_kg && (
                <Button variant="ghost" size="sm" onClick={() => set("cargo_usd_per_kg")(suggestion.usd_per_kg)}>
                  {t("calculator.cargoApply")}
                </Button>
              )}
            </div>
          )}
          <NumberInput label={t("calculator.extra_uzs")} value={values.extra_uzs} onValueChange={set("extra_uzs")} optional />
        </fieldset>
        <fieldset className="calculator__group">
          <legend className="h4">{t("calculator.group.uzum")}</legend>
          <NumberInput label={t("calculator.price")} value={values.price} onValueChange={set("price")} />
          <NumberInput label={t("calculator.commission_pct")} value={values.commission_pct} onValueChange={set("commission_pct")} suffix="%" help={t("calculator.commissionHelp")} />
          <NumberInput
            label={t("calculator.tax_pct")}
            value={values.tax_pct}
            onValueChange={set("tax_pct")}
            suffix="%"
            optional
            help={defaults.tax_pct === null ? t("calculator.taxNone") : defaults.tax_on_payout ? t("calculator.taxPayout") : t("calculator.taxFromProfile")}
          />
          <NumberInput label={t("calculator.ads_pct")} value={values.ads_pct} onValueChange={set("ads_pct")} suffix="%" optional />
          <NumberInput label={t("calculator.packaging_uzs")} value={values.packaging_uzs} onValueChange={set("packaging_uzs")} optional />
          <NumberInput label={t("calculator.target_margin_pct")} value={values.target_margin_pct} onValueChange={set("target_margin_pct")} suffix="%" optional help={t("calculator.targetHelp")} />
        </fieldset>
        <fieldset className="calculator__group">
          <legend className="h4">{t("calculator.group.rates")}</legend>
          <NumberInput label={t("calculator.cny_rate")} value={values.cny_rate} onValueChange={set("cny_rate")} optional help={rateHint(rate.cny)} />
          <NumberInput label={t("calculator.usd_rate")} value={values.usd_rate} onValueChange={set("usd_rate")} optional help={rateHint(rate.usd)} />
        </fieldset>
        <fieldset className="calculator__group" data-testid="scenarios">
          <legend className="h4">{t("calculator.scenario.title")}</legend>
          <TextInput label={t("calculator.scenario.name")} value={scenarioName} onValueChange={setScenarioName} maxLength={80} />
          <Button size="sm" disabled={scenarioName.trim() === "" || input === null || save.isPending} onClick={() => save.mutate()}>
            {t("calculator.scenario.save")}
          </Button>
          {input === null && <p className="caption">{t("calculator.scenario.needInput")}</p>}
          {scenarios.length === 0 ? (
            <p className="caption">{t("calculator.scenario.empty")}</p>
          ) : (
            <ul className="calculator__scenarios">
              {scenarios.map((s) => (
                <li key={s.id}>
                  <span>{s.name}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setValues(fromScenario(s.inputs));
                      setScenarioName(s.name);
                    }}
                  >
                    {t("calculator.scenario.open")}
                  </Button>
                  <Button variant="ghost" size="sm" aria-label={t("calculator.scenario.delete", { name: s.name })} onClick={() => remove.mutate(s.id)}>
                    ✕
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
        <Button variant="ghost" size="sm" disabled={JSON.stringify(values) === JSON.stringify(start)} onClick={() => setValues(start)}>
          {t("calculator.reset")}
        </Button>
      </div>
      <div className="calculator__result" role="status" aria-live="polite" aria-busy={result.isFetching || undefined}>
        {failure !== null ? (
          <p className="ui-text--negative" role="alert">
            {failure}
          </p>
        ) : c === undefined ? (
          <p className="muted">{t("calculator.needInput")}</p>
        ) : (
          <dl className="calculator__list">
            <div className="calculator__main">
              <dt>{t("calculator.profit")}</dt>
              <dd className={Number(c.unit.profit) < 0 ? "ui-text--negative" : "ui-text--positive"} data-testid="calc-profit">
                {f.money(c.unit.profit)}
              </dd>
            </div>
            <div>
              <dt>{t("terms.margin")}</dt>
              <dd>{c.unit.margin === null ? "—" : f.percent(c.unit.margin)}</dd>
            </div>
            <div>
              <dt>{t("terms.roi")}</dt>
              <dd>{c.unit.roi === null ? "—" : f.percent(c.unit.roi)}</dd>
            </div>
            <div className="calculator__section">
              <dt>{t("calculator.result.unitCost")}</dt>
              <dd data-testid="calc-unit-cost">{f.money(c.landed.unit_cost)}</dd>
            </div>
            <div>
              <dt>{t("calculator.result.goods")}</dt>
              <dd>{f.money(c.landed.goods)}</dd>
            </div>
            <div>
              <dt>{t("calculator.result.china")}</dt>
              <dd>{f.money(c.landed.china)}</dd>
            </div>
            <div>
              <dt>{t("calculator.result.cargo")}</dt>
              <dd>
                {f.money(c.landed.cargo)}
                {c.landed.cargo_basis && <span className="caption"> {t(`calculator.result.basis.${c.landed.cargo_basis}`)}</span>}
              </dd>
            </div>
            <div>
              <dt>{t("calculator.result.extra")}</dt>
              <dd>{f.money(c.landed.extra)}</dd>
            </div>
            <div className="calculator__section">
              <dt>
                {t("calculator.result.logistics")} {help("logistics", t("calculator.result.logistics"))}
              </dt>
              <dd data-testid="calc-logistics">
                {f.money(c.logistics.fee)}
                <span className="caption"> {c.logistics.source === "dims" ? t("calculator.result.liters", { value: f.number(c.logistics.liters ?? 0) }) : t("calculator.result.noDims")}</span>
              </dd>
            </div>
            <div>
              <dt>{t("calculator.result.commission")}</dt>
              <dd>{f.money(c.unit.commission)}</dd>
            </div>
            <div>
              <dt>{t("calculator.result.tax", { value: f.number(c.tax_pct, { digits: 1, trim: true }) })}</dt>
              <dd>{f.money(c.unit.tax)}</dd>
            </div>
            <div>
              <dt>{t("calculator.result.ads")}</dt>
              <dd>{f.money(c.unit.ads)}</dd>
            </div>
            <div className="calculator__section">
              <dt>
                {t("calculator.result.breakeven")} {help("breakeven", t("calculator.result.breakeven"))}
              </dt>
              <dd data-testid="calc-breakeven">{c.unit.breakeven === null ? t("calculator.result.noPrice") : f.money(c.unit.breakeven)}</dd>
            </div>
            {values.target_margin_pct !== null && (
              <div>
                <dt>
                  {t("calculator.result.targetPrice", { value: f.number(values.target_margin_pct, { digits: 0, trim: true }) })} {help("targetPrice", t("calculator.result.targetPriceShort"))}
                </dt>
                <dd data-testid="calc-target">{c.unit.target_price === null ? t("calculator.result.noPrice") : f.money(c.unit.target_price)}</dd>
              </div>
            )}
          </dl>
        )}
        {c !== undefined && Number(c.unit.share_pct) >= 100 && <p className="ui-text--negative">{t("calculator.shareOver", { value: f.number(c.unit.share_pct, { digits: 1, trim: true }) })}</p>}
      </div>
    </div>
  );
}
