// Bo'sh holat, skelet, progress (04 §5).
import { useEffect, useState, type ReactNode } from "react";

import { cx } from "./cx";

/** Bo'sh holat: nima bo'lishi kerak + bitta harakat. */
export function EmptyState({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <section className="ui-empty">
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </section>
  );
}

/** Kechikkan ko'rinish: tez yuklanishda skelet miltillamasin (04 §5: 300 ms dan uzoq bo'lsa). */
export function useDelayed(ms = 300): boolean {
  const [shown, setShown] = useState(ms <= 0);
  useEffect(() => {
    if (ms <= 0) return;
    const id = setTimeout(() => setShown(true), ms);
    return () => clearTimeout(id);
  }, [ms]);
  return shown;
}

export function Skeleton({ lines = 3, delay = 300, label }: { lines?: number; delay?: number; label: string }) {
  const shown = useDelayed(delay);
  return (
    <div className="ui-skeleton" role="status" aria-label={label} aria-busy>
      {shown &&
        Array.from({ length: lines }, (_, i) => (
          <span key={i} className={cx("ui-skeleton__line", i === lines - 1 && "is-short")} />
        ))}
    </div>
  );
}

export function ProgressBar({ value, max, label, detail }: { value: number; max: number; label: string; detail?: string }) {
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div className="ui-progress">
      <div className="ui-progress__head">
        <span>{label}</span>
        {detail && <span className="num">{detail}</span>}
      </div>
      <div
        className="ui-progress__track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <span className="ui-progress__bar" style={{ inlineSize: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}
