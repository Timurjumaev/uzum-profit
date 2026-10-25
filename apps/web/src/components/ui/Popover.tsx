// Popover va Tooltip (04 §5). Popover — tugma bilan ochiladi, tashqarida bosilsa yoki Esc bilan yopiladi (fokus
// tugmaga qaytadi), modal emas. Tooltip — hover va fokusda, `aria-describedby`; muhim ma'lumot faqat tooltip'da emas.
import { cloneElement, useEffect, useId, useRef, useState, type ReactElement, type ReactNode } from "react";

import { cx } from "./cx";

export type PopoverProps = {
  /** Ochuvchi tugma ichidagi matn yoki ikon. */
  trigger: ReactNode;
  /** Tugmaning ekran o'quvchi uchun nomi (ikon bo'lsa majburiy). */
  label?: string;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "start" | "end";
  triggerClassName?: string;
  /** Boshqariladigan rejim. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function Popover({ trigger, label, children, align = "start", triggerClassName, open, onOpenChange }: PopoverProps) {
  const [own, setOwn] = useState(false);
  const isOpen = open ?? own;
  const setOpen = (value: boolean) => {
    if (open === undefined) setOwn(value);
    onOpenChange?.(value);
  };
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  const triggerId = `${id}-trigger`;
  // Tanlov bilan yopilganda fokus tugmaga qaytadi (tashqarida bosilganda — yo'q, foydalanuvchi boshqa joyni tanladi).
  const close = () => {
    setOpen(false);
    document.getElementById(triggerId)?.focus();
  };
  useEffect(() => {
    if (!isOpen) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
    // setOpen har renderda yangi — faqat ochilish holatiga bog'liq.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);
  return (
    <div className="ui-popover" ref={root}>
      <button
        ref={button}
        id={triggerId}
        type="button"
        className={triggerClassName ?? "ui-btn ui-btn--secondary ui-btn--md"}
        aria-expanded={isOpen}
        aria-controls={id}
        aria-label={label}
        onClick={() => setOpen(!isOpen)}
      >
        {trigger}
      </button>
      {isOpen && (
        <div id={id} className={cx("ui-popover__panel", `ui-popover__panel--${align}`)} role="group" aria-label={label}>
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}

export function Tooltip({ text, children }: { text: string; children: ReactElement<{ "aria-describedby"?: string }> }) {
  const [shown, setShown] = useState(false);
  const id = useId();
  return (
    <span
      className="ui-tooltip"
      onMouseEnter={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      onFocus={() => setShown(true)}
      onBlur={() => setShown(false)}
      onKeyDown={(e) => e.key === "Escape" && setShown(false)}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span id={id} role="tooltip" className={cx("ui-tooltip__bubble", shown && "is-shown")}>
        {text}
      </span>
    </span>
  );
}
