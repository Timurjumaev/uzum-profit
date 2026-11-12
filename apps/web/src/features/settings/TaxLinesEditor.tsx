// Soliq qatorlari muharriri (F11, ADR-058): har qator — alohida soliq, foizli (baza × stavka) yoki qat'iy (so'm yoki
// n × BHM, oy / chorak / yil). Tayyor shablon qatorlarni to'ldiradi, keyin hammasi tahrirlanadi. Hisob yo'q — faqat
// kiritish (formula serverda, tamoyil 4); BHM qiymati ma'lumotnomadan ko'rsatiladi.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, NumberInput, Select, TextInput } from "../../components/ui";
import type { TaxRate } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { BASES, LINE_PERIODS, MAX_TAX_LINES, TAX_TEMPLATES, lineValid, newLine, taxTemplate, type LineDraft, type TaxTemplate } from "./model";

type Props = {
  lines: LineDraft[];
  onChange: (lines: LineDraft[]) => void;
  rates: TaxRate[];
  /** Joriy BHM (so'm), ma'lumotnomadan; yo'q bo'lsa `null`. */
  bhm: string | null;
};

export function TaxLinesEditor({ lines, onChange, rates, bhm }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  // Tanlov tanlangan shablonni ko'rsatadi (qo'llangach "Tanlang…" ga qaytmaydi); qatorlar qo'lda o'zgarsa — "tahrirlangan".
  const [template, setTemplate] = useState<TaxTemplate | "custom" | "">(lines.length > 0 ? "custom" : "");
  const edit = (next: LineDraft[]) => {
    setTemplate("custom");
    onChange(next);
  };
  const apply = (kind: TaxTemplate) => {
    setTemplate(kind);
    onChange(taxTemplate(kind, rates, names));
  };
  const set = (key: string, patch: Partial<LineDraft>) => edit(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const names = { turnover: t("settings.tax.lines.legacyName"), social: t("settings.tax.lines.socialName") };
  return (
    <fieldset className="settings-fieldset tax-lines">
      <legend className="h4">{t("settings.tax.lines.title")}</legend>
      <p className="caption">{t("settings.tax.lines.lead")}</p>
      <Select
        label={t("settings.tax.lines.template.label")}
        help={t("settings.tax.lines.template.help")}
        value={template}
        onValueChange={(v) => v && v !== "custom" && apply(v as TaxTemplate)}
        options={[
          { value: "", label: t("settings.tax.lines.template.placeholder"), disabled: template !== "" },
          ...TAX_TEMPLATES.map((k) => ({ value: k, label: t(`settings.tax.lines.template.${k}`) })),
          ...(template === "custom" ? [{ value: "custom", label: t("settings.tax.lines.template.custom"), disabled: true }] : []),
        ]}
      />
      {template !== "" && template !== "custom" && (
        <p className="caption" role="status">
          {t("settings.tax.lines.template.applied", { n: lines.length })}
        </p>
      )}
      {lines.length === 0 && <p className="caption">{t("settings.tax.lines.none")}</p>}
      {lines.map((line, i) => {
        const n = i + 1;
        return (
          <div key={line.key} className="tax-line" role="group" aria-label={t("settings.tax.lines.lineN", { n })}>
            <TextInput label={t("settings.tax.lines.name")} value={line.name} maxLength={60} onValueChange={(name) => set(line.key, { name })} />
            <Select
              label={t("settings.tax.lines.kindLabel")}
              value={line.kind}
              onValueChange={(kind) => set(line.key, { kind: kind as LineDraft["kind"], mode: kind === "fixed" ? "bhm" : "sum" })}
              options={(["percent", "fixed"] as const).map((k) => ({ value: k, label: t(`settings.tax.lines.kind.${k}`) }))}
            />
            {line.kind === "percent" ? (
              <>
                <NumberInput label={t("settings.tax.rate")} suffix="%" value={line.rate} onValueChange={(rate) => set(line.key, { rate })} />
                <Select label={t("settings.tax.baseLabel")} value={line.base} onValueChange={(base) => set(line.key, { base: base as LineDraft["base"] })} options={BASES.map((b) => ({ value: b, label: t(`settings.tax.base.${b}`) }))} />
              </>
            ) : (
              <>
                <Select
                  label={t("settings.tax.lines.mode.label")}
                  value={line.mode}
                  onValueChange={(mode) => set(line.key, { mode: mode as LineDraft["mode"] })}
                  options={(["bhm", "sum"] as const).map((k) => ({ value: k, label: t(`settings.tax.lines.mode.${k}`) }))}
                />
                {line.mode === "bhm" ? (
                  <NumberInput
                    label={t("settings.tax.lines.bhmCount")}
                    help={bhm === null ? t("settings.tax.lines.bhmUnknown") : t("settings.tax.lines.bhmHelp", { amount: f.money(bhm) })}
                    value={line.bhm}
                    onValueChange={(bhmCount) => set(line.key, { bhm: bhmCount })}
                  />
                ) : (
                  <NumberInput label={t("settings.tax.lines.amount")} suffix={t("settings.tax.lines.sum")} value={line.amount} onValueChange={(amount) => set(line.key, { amount })} />
                )}
                <Select
                  label={t("settings.tax.lines.period.label")}
                  help={t("settings.tax.lines.period.help")}
                  value={line.period}
                  onValueChange={(period) => set(line.key, { period: period as LineDraft["period"] })}
                  options={LINE_PERIODS.map((p) => ({ value: p, label: t(`settings.tax.lines.period.${p}`) }))}
                />
              </>
            )}
            <div className="tax-line__actions">
              {!lineValid(line) && <span className="caption tax-line__hint">{t("settings.tax.lines.incomplete")}</span>}
              <Button size="sm" variant="ghost" onClick={() => edit(lines.filter((l) => l.key !== line.key))}>
                {t("settings.tax.lines.remove")}
              </Button>
            </div>
          </div>
        );
      })}
      <div className="settings-actions">
        <Button variant="secondary" size="sm" disabled={lines.length >= MAX_TAX_LINES} onClick={() => edit([...lines, newLine("percent")])}>
          {t("settings.tax.lines.add")}
        </Button>
        {lines.length >= MAX_TAX_LINES && <span className="caption">{t("settings.tax.lines.max", { n: MAX_TAX_LINES })}</span>}
      </div>
    </fieldset>
  );
}
