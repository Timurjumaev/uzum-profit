// Solishtirish (04 §5): yo'q / oldingi davr / o'tgan yil — radio guruh (strelkalar bilan).
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { cx } from "./cx";

export type CompareMode = "none" | "previous" | "lastYear";
const MODES: CompareMode[] = ["none", "previous", "lastYear"];

export function CompareToggle({ value, onChange }: { value: CompareMode; onChange: (mode: CompareMode) => void }) {
  const { t } = useTranslation();
  const name = useId();
  return (
    <fieldset className="ui-segmented">
      <legend className="ui-visually-hidden">{t("ui.compare.label")}</legend>
      {MODES.map((mode) => (
        <label key={mode} className={cx("ui-segmented__item", value === mode && "is-checked")}>
          <input type="radio" name={name} value={mode} checked={value === mode} onChange={() => onChange(mode)} />
          {t(`ui.compare.${mode}`)}
        </label>
      ))}
    </fieldset>
  );
}
