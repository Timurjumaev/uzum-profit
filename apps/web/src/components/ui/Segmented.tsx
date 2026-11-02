// Segmentli tanlov (04 §5): bir nechta ko'rinishdan bittasi — radio guruh (strelkalar bilan), `ui-segmented` uslubi.
// Masalan, grafikda "Sof foyda | Tushum" yoki tor ekranda hisob varag'i ustuni "Naqd | Kutilayotgan | Jami".
import { useId } from "react";

import { cx } from "./cx";

export type SegmentedOption<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  /** Guruh nomi (ekran o'quvchi uchun, ko'rinmaydi). */
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
};

export function Segmented<T extends string>({ label, options, value, onChange, className }: Props<T>) {
  const name = useId();
  return (
    <fieldset className={cx("ui-segmented", className)}>
      <legend className="ui-visually-hidden">{label}</legend>
      {options.map((o) => (
        <label key={o.value} className={cx("ui-segmented__item", value === o.value && "is-checked")}>
          <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          {o.label}
        </label>
      ))}
    </fieldset>
  );
}
