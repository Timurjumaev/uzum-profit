// Unit kalkulyator (M6, F35/F36): narx, reklama %, tannarx o'zgarsa nima bo'ladi. Boshlang'ich qiymatlar SKU
// sahifasi javobidan (davr haqiqati, manbasi ko'rsatiladi; logistika — me'yoriy, bonussiz, F40); hisob serverda
// (`/unit-calc`, tamoyil 4) — bu yerda faqat kiritish va ko'rsatish. Qiymat yo'q bo'lsa taxmin qilinmaydi: maydon bo'sh.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { unitCalcQuery, type UnitCalcInput } from "../../app/query";
import { Button, FormulaPopover, MoneyInput, NumberInput } from "../../components/ui";
import type { SkuCalcDefaults } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Field = "price" | "unit_cost" | "logistics" | "packaging" | "commission_pct" | "tax_pct" | "ads_pct" | "target_margin_pct";
type Values = Record<Field, string | null>;

const DEBOUNCE_MS = 300;

export function initialValues(d: SkuCalcDefaults): Values {
  return {
    price: d.price,
    unit_cost: d.unit_cost,
    logistics: d.logistics,
    packaging: d.packaging,
    commission_pct: d.commission_pct,
    tax_pct: d.tax_pct,
    ads_pct: d.ads_pct,
    target_margin_pct: null,
  };
}

/** Hisob uchun kiritish: majburiy maydonlar (narx, tannarx, komissiya) bo'lmasa `null`; qolgan bo'sh maydon — 0. */
export function toInput(v: Values): UnitCalcInput | null {
  if (v.price === null || v.unit_cost === null || v.commission_pct === null) return null;
  return {
    price: v.price,
    unit_cost: v.unit_cost,
    logistics: v.logistics ?? "0",
    packaging: v.packaging ?? "0",
    commission_pct: v.commission_pct,
    tax_pct: v.tax_pct ?? "0",
    ads_pct: v.ads_pct ?? "0",
    target_margin_pct: v.target_margin_pct,
  };
}

function useDebounced<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setOut(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return out;
}

export function Calculator({ orgId, defaults }: { orgId: string; defaults: SkuCalcDefaults }) {
  const { t } = useTranslation();
  const f = useFormat();
  const start = useMemo(() => initialValues(defaults), [defaults]);
  const [values, setValues] = useState<Values>(start);
  const [seen, setSeen] = useState(defaults);
  if (seen !== defaults) {
    // Davr yoki SKU almashdi — yangi boshlang'ich qiymatlar.
    setSeen(defaults);
    setValues(start);
  }
  const input = useDebounced(toInput(values), DEBOUNCE_MS);
  const result = useQuery({ ...unitCalcQuery(orgId, input!), enabled: input !== null, placeholderData: keepPreviousData });
  const set = (field: Field) => (value: string | null) => setValues((v) => ({ ...v, [field]: value }));
  const hint = (field: Exclude<Field, "target_margin_pct" | "packaging">) => {
    const source = defaults.sources[field];
    return source ? t(`products.calc.source.${field}.${source}`) : t("products.calc.enter");
  };
  const c = input === null ? undefined : result.data;
  const changed = JSON.stringify(values) !== JSON.stringify(start);
  const help = (key: string, metric: string) => (
    <FormulaPopover metric={metric} code={t(`home.formula.${key}.code`)} formula={t(`home.formula.${key}.formula`)} source={t(`home.formula.${key}.source`)} />
  );
  return (
    <section className="sku-calc" aria-labelledby="sku-calc-title">
      <div className="sku-calc__head">
        <h2 id="sku-calc-title" className="h3">
          {t("products.calc.title")}
        </h2>
        <Button variant="ghost" size="sm" disabled={!changed} onClick={() => setValues(start)}>
          {t("products.calc.reset")}
        </Button>
      </div>
      <p className="caption">{t("products.calc.lead")}</p>
      <div className="sku-calc__grid">
        <div className="sku-calc__inputs">
          <MoneyInput label={t("products.calc.price")} value={values.price} onValueChange={set("price")} help={hint("price")} />
          <MoneyInput label={t("products.calc.unitCost")} value={values.unit_cost} onValueChange={set("unit_cost")} help={hint("unit_cost")} />
          <MoneyInput label={t("products.calc.logistics")} value={values.logistics} onValueChange={set("logistics")} help={hint("logistics")} />
          <MoneyInput label={t("products.calc.packaging")} value={values.packaging} onValueChange={set("packaging")} />
          <NumberInput label={t("products.calc.commission")} value={values.commission_pct} onValueChange={set("commission_pct")} suffix="%" help={hint("commission_pct")} />
          <NumberInput label={t("products.calc.tax")} value={values.tax_pct} onValueChange={set("tax_pct")} suffix="%" help={hint("tax_pct")} />
          <NumberInput label={t("products.calc.ads")} value={values.ads_pct} onValueChange={set("ads_pct")} suffix="%" help={hint("ads_pct")} />
          <NumberInput
            label={t("products.calc.target")}
            value={values.target_margin_pct}
            onValueChange={set("target_margin_pct")}
            suffix="%"
            optional
            help={t("products.calc.targetHelp")}
          />
        </div>
        <div className="sku-calc__result" role="status" aria-live="polite" aria-busy={result.isFetching || undefined}>
          {c === undefined ? (
            <p className="muted">{t("products.calc.needInput")}</p>
          ) : (
            <dl className="sku-calc__list">
              <div className="sku-calc__main">
                <dt>{t("products.calc.profit")}</dt>
                <dd className={Number(c.profit) < 0 ? "ui-text--negative" : undefined} data-testid="calc-profit">
                  {f.money(c.profit)}
                </dd>
              </div>
              <div>
                <dt>{t("terms.margin")}</dt>
                <dd>{c.margin === null ? "—" : f.percent(c.margin)}</dd>
              </div>
              <div>
                <dt>{t("terms.roi")}</dt>
                <dd>{c.roi === null ? "—" : f.percent(c.roi)}</dd>
              </div>
              <div>
                <dt>{t("products.calc.fixed")}</dt>
                <dd>{f.money(c.fixed)}</dd>
              </div>
              <div>
                <dt>
                  {t("products.calc.breakeven")} {help("breakeven", t("products.calc.breakeven"))}
                </dt>
                <dd data-testid="calc-breakeven">{c.breakeven === null ? t("products.calc.noPrice") : f.money(c.breakeven)}</dd>
              </div>
              {values.target_margin_pct !== null && (
                <div>
                  <dt>
                    {t("products.calc.targetPrice", { value: f.number(values.target_margin_pct, { digits: 0, trim: true }) })}{" "}
                    {help("targetPrice", t("products.calc.targetPriceShort"))}
                  </dt>
                  <dd data-testid="calc-target">{c.target_price === null ? t("products.calc.noPrice") : f.money(c.target_price)}</dd>
                </div>
              )}
              <div className="sku-calc__parts">
                <dt>{t("products.calc.parts")}</dt>
                <dd>
                  {t("products.calc.partsText", { commission: f.money(c.commission), tax: f.money(c.tax), ads: f.money(c.ads) })}
                </dd>
              </div>
            </dl>
          )}
          {c !== undefined && Number(c.share_pct) >= 100 && <p className="ui-text--negative">{t("products.calc.shareOver", { value: f.number(c.share_pct, { digits: 1, trim: true }) })}</p>}
        </div>
      </div>
    </section>
  );
}
