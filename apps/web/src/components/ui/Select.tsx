// Oddiy tanlov (native select — mobil va klaviatura bepul). Qidiruvli tanlov — `Combobox`.
import type { SelectHTMLAttributes } from "react";

import { cx } from "./cx";
import { Field } from "./Field";

export type SelectOption = { value: string; label: string; disabled?: boolean };

export type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange" | "id"> & {
  label: string;
  help?: string;
  error?: string | null;
  options: SelectOption[];
  value: string;
  onValueChange: (value: string) => void;
};

export function Select({ label, help, error, options, value, onValueChange, className, ...rest }: SelectProps) {
  return (
    <Field label={label} help={help} error={error}>
      {({ id, describedBy, invalid }) => (
        <select
          id={id}
          className={cx("ui-input", "ui-select", className)}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}
