// KPI (04 §5): yorliq, qiymat (proportsional raqam), o'zgarish — ishora + nom bilan davr, rang = yo'nalish × yaxshimi
// (xarajat o'sishi — yomon), 12 nuqtali sparkline (bezak, `aria-hidden`; raqam matnda bor).
import type { ReactNode } from "react";

import { useFormat } from "../../lib/i18n";
import { cx } from "./cx";

export type KpiProps = {
  label: string;
  /** Formatlangan qiymat (pul — `f.money`). */
  value: string;
  /** O'zgarish ulushi ("0.124"); yo'q bo'lsa ko'rsatilmaydi. */
  change?: string | null;
  /** O'zgarish matni: "oldingi davrga nisbatan". */
  changeLabel?: string;
  /** Qaysi yo'nalish yaxshi: foyda — "up", xarajat — "down". */
  good?: "up" | "down";
  spark?: number[];
  help?: ReactNode;
  /** Qiymat ostidagi izoh (masalan, marja yonida tannarxsiz qism ulushi). */
  note?: string;
};

export function changeTone(change: string, good: "up" | "down"): "positive" | "negative" | "neutral" {
  const sign = Math.sign(Number(change));
  if (sign === 0) return "neutral";
  return (sign > 0) === (good === "up") ? "positive" : "negative";
}

export function Sparkline({ points, width = 96, height = 28 }: { points: number[]; width?: number; height?: number }) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const span = Math.max(...points) - min || 1;
  const step = width / (points.length - 1);
  const d = points.map((p, i) => `${(i * step).toFixed(1)},${(height - 2 - ((p - min) / span) * (height - 4)).toFixed(1)}`).join(" ");
  return (
    <svg className="ui-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden focusable="false">
      <polyline points={d} fill="none" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function Kpi({ label, value, change, changeLabel, good = "up", spark, help, note }: KpiProps) {
  const f = useFormat();
  const tone = change != null ? changeTone(change, good) : null;
  return (
    <div className="ui-kpi">
      <div className="ui-kpi__label label">
        {label}
        {help}
      </div>
      <div className="kpi">{value}</div>
      {note && <div className="caption ui-kpi__note">{note}</div>}
      {change != null && (
        <div className={cx("ui-kpi__change", `ui-text--${tone}`)}>
          {f.change(change)}
          {changeLabel && <span className="caption"> {changeLabel}</span>}
        </div>
      )}
      {spark && <Sparkline points={spark} />}
    </div>
  );
}
