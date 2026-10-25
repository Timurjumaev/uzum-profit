// Qidiruvli tanlov (04 §5, §8.3): lotin/kirill va apostrof turlaridan qat'i nazar (`searchKey`), klaviatura bilan
// (↑ ↓ Enter Esc), ARIA combobox + listbox. SKU qidiruvida kichik rasm (`thumb`).
import { useId, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { searchKey } from "../../lib/i18n/translit";
import { cx } from "./cx";
import { Field } from "./Field";

export type ComboOption = { value: string; label: string; hint?: string; keywords?: string; thumb?: ReactNode };

export type ComboboxProps = {
  label: string;
  help?: string;
  options: ComboOption[];
  value: string | null;
  onValueChange: (value: string | null) => void;
  placeholder?: string;
  limit?: number;
};

/** Qidiruv kaliti apostrofsiz: "galla" ham "gʻalla" ni topadi (foydalanuvchi ko'pincha belgisiz yozadi). */
const loose = (text: string) => searchKey(text).replaceAll("'", "");

export function filterOptions(options: ComboOption[], query: string): ComboOption[] {
  const words = loose(query).split(" ").filter(Boolean);
  if (words.length === 0) return options;
  return options.filter((o) => {
    const hay = loose(`${o.label} ${o.hint ?? ""} ${o.keywords ?? ""}`);
    return words.every((w) => hay.includes(w));
  });
}

export function Combobox({ label, help, options, value, onValueChange, placeholder, limit = 50 }: ComboboxProps) {
  const { t } = useTranslation();
  const listId = useId();
  const selected = options.find((o) => o.value === value) ?? null;
  const [query, setQuery] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const shown = useMemo(() => filterOptions(options, query ?? "").slice(0, limit), [options, query, limit]);
  const choose = (option: ComboOption) => {
    onValueChange(option.value);
    setQuery(null);
    setOpen(false);
  };
  const optionId = (i: number) => `${listId}-${i}`;
  return (
    <Field label={label} help={help}>
      {({ id, describedBy }) => (
        <div className="ui-combobox">
          <input
            id={id}
            className="ui-input"
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={open && shown[active] ? optionId(active) : undefined}
            aria-describedby={describedBy}
            autoComplete="off"
            placeholder={placeholder ?? t("ui.search")}
            value={query ?? selected?.label ?? ""}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => {
              setOpen(false);
              setQuery(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setOpen(true);
                setActive((i) => Math.min(i + 1, shown.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && open && shown[active]) {
                e.preventDefault();
                choose(shown[active]);
              } else if (e.key === "Escape") {
                setOpen(false);
                setQuery(null);
              }
            }}
          />
          {open && (
            <ul id={listId} role="listbox" className="ui-combobox__list" aria-label={label}>
              {shown.length === 0 && <li className="ui-combobox__empty">{t("ui.noResults")}</li>}
              {shown.map((o, i) => (
                <li
                  key={o.value}
                  id={optionId(i)}
                  role="option"
                  aria-selected={o.value === value}
                  className={cx("ui-combobox__option", i === active && "is-active")}
                  onMouseDown={(e) => {
                    e.preventDefault(); // blur'dan oldin tanlansin
                    choose(o);
                  }}
                  onMouseEnter={() => setActive(i)}
                >
                  {o.thumb}
                  <span>
                    {o.label}
                    {o.hint && <span className="caption"> · {o.hint}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Field>
  );
}
