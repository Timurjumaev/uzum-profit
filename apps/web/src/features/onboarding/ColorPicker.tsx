// Do'kon rangi (M2 2-qadam): 8 ta kategoriya rangi (04 §4.3), qat'iy tartibda; do'kon 1 doim 1-rang. Tanlov — radio
// guruh (klaviatura: strelkalar), rang nomi matnda (rang yolg'iz emas). Saqlanadigan qiymat — HEX (API: `#RRGGBB`).
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { cx } from "../../components/ui/cx";
import { chartSlots } from "../../styles/tokens";

/** Saqlanadigan ranglar (yorug' rejim qiymatlari; grafiklar ularni mavzuga qarab slot orqali oladi). */
export const SHOP_COLORS: readonly string[] = chartSlots.light;

/** Do'kon tartib raqamiga standart rang; 8 tadan keyin — rangsiz (aylanib takrorlanmaydi, 04 §4.3). */
export const defaultColor = (index: number): string | null => SHOP_COLORS[index] ?? null;

export function ColorPicker({ label, value, onChange }: { label: string; value: string | null; onChange: (color: string) => void }) {
  const { t } = useTranslation();
  const name = useId();
  return (
    <fieldset className="colorpicker">
      <legend className="label">{label}</legend>
      <div className="colorpicker__list">
        {SHOP_COLORS.map((color, i) => (
          <label key={color} className={cx("colorpicker__item", value?.toLowerCase() === color.toLowerCase() && "is-checked")}>
            <input type="radio" name={name} value={color} checked={value?.toLowerCase() === color.toLowerCase()} onChange={() => onChange(color)} />
            <span className="colorpicker__swatch" style={{ background: color }} aria-hidden />
            <span className="ui-visually-hidden">{t(`onboarding.colors.${i + 1}`)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
