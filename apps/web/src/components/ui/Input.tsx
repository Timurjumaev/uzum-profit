// Matn, son va pul maydonlari (04 §5). Son va pul: "1 234,5", "1234.5", "1 234 567" qabul qilinadi
// (`parseNumber`), qiymat API uchun nuqtali satr ("1234.5"); fokusdan chiqqanda formatlanadi. Pul o'ngga tekislanadi,
// valyuta qo'shimchasi bilan.
import { useState, type InputHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";

import { formatNumber, parseNumber } from "../../lib/format";
import { useFormat } from "../../lib/i18n";
import { cx } from "./cx";
import { Field } from "./Field";

type Base = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "id"> & {
  label: string;
  help?: string;
  error?: string | null;
  optional?: boolean;
};

export type TextInputProps = Base & { value: string; onValueChange: (value: string) => void };

export function TextInput({ label, help, error, optional, value, onValueChange, className, ...rest }: TextInputProps) {
  return (
    <Field label={label} help={help} error={error} optional={optional}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          className={cx("ui-input", className)}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          {...rest}
        />
      )}
    </Field>
  );
}

export type NumberInputProps = Base & {
  /** Nuqtali satr ("1234.5") yoki `null` (bo'sh). */
  value: string | null;
  onValueChange: (value: string | null) => void;
  /** Ko'rsatishdagi kasr xonalari (standart: kiritilganicha). */
  digits?: number;
  suffix?: string;
};

function display(value: string | null, digits?: number): string {
  if (value === null) return "";
  return digits === undefined ? formatNumber(value, { digits: value.split(".")[1]?.length ?? 0 }) : formatNumber(value, { digits });
}

export function NumberInput({
  label,
  help,
  error,
  optional,
  value,
  onValueChange,
  digits,
  suffix,
  className,
  onBlur,
  ...rest
}: NumberInputProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string | null>(null);
  const invalidDraft = draft !== null && draft.trim() !== "" && parseNumber(draft) === null;
  return (
    <Field
      label={label}
      help={help}
      error={error ?? (invalidDraft ? t("ui.invalidNumber") : null)}
      optional={optional}
    >
      {({ id, describedBy, invalid }) => (
        <div className={cx("ui-input-wrap", suffix && "has-suffix")}>
          <input
            id={id}
            className={cx("ui-input", "ui-input--number", className)}
            inputMode="decimal"
            autoComplete="off"
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            value={draft ?? display(value, digits)}
            onChange={(e) => {
              setDraft(e.target.value);
              const parsed = parseNumber(e.target.value);
              if (parsed !== null || e.target.value.trim() === "") onValueChange(parsed);
            }}
            onBlur={(e) => {
              if (!invalidDraft) setDraft(null);
              onBlur?.(e);
            }}
            {...rest}
          />
          {suffix && (
            <span className="ui-input__suffix" aria-hidden>
              {suffix}
            </span>
          )}
        </div>
      )}
    </Field>
  );
}

export type MoneyInputProps = Omit<NumberInputProps, "suffix" | "digits"> & { currency?: "UZS" | "USD" | "CNY" | "EUR" | "RUB" };

const SIGN: Record<string, string> = { USD: "$", CNY: "¥", EUR: "€", RUB: "₽" };

export function MoneyInput({ currency = "UZS", ...rest }: MoneyInputProps) {
  const f = useFormat();
  const suffix = currency === "UZS" ? f.money(0).replace(/^0\u00A0/, "") : SIGN[currency];
  return <NumberInput {...rest} digits={currency === "USD" || currency === "EUR" ? 2 : undefined} suffix={suffix} />;
}
