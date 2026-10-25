// Forma maydoni (04 §5): yorliq tepada, yordam matni pastda, xato — matn bilan (`aria-invalid`, `aria-describedby`).
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export type FieldControl = { id: string; describedBy?: string; invalid: boolean };

export type FieldProps = {
  label: string;
  help?: string;
  error?: string | null;
  optional?: boolean;
  children: (control: FieldControl) => ReactNode;
};

export function Field({ label, help, error, optional, children }: FieldProps) {
  const { t } = useTranslation();
  const id = useId();
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={id}>
        {label}
        {optional && <span className="ui-field__optional"> ({t("ui.optional")})</span>}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {error && (
        <p id={errorId} className="ui-field__error" role="alert">
          {error}
        </p>
      )}
      {help && (
        <p id={helpId} className="ui-field__help">
          {help}
        </p>
      )}
    </div>
  );
}
