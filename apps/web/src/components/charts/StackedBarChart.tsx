// Qatlamli ustun (04 §5): xarajatlar tarkibi — rollar ketma-ket slotlarda (2–8, 04 §4.3).
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { describeSeries } from "./describe";
import { EChart } from "./EChart";
import { ChartFrame } from "./ChartFrame";
import { stackedBarOption, valueText, xText } from "./options";
import type { SeriesInput, Unit, Value, XKind } from "./types";
import { useChartCtx } from "./useChartCtx";

export type StackedBarChartProps = {
  title: string;
  x: string[];
  xKind?: XKind;
  unit?: Unit;
  series: SeriesInput[];
  /** API'dan tayyor jami (tooltip va jadvalda "Jami"); grafik o'zi qo'shmaydi. */
  totals?: Value[];
  height?: number;
};

export function StackedBarChart({ title, x, xKind = "month", unit = "money", series, totals, height }: StackedBarChartProps) {
  const { t } = useTranslation();
  const ctx = useChartCtx();
  const totalLabel = t("charts.total");
  const option = useMemo(
    () => stackedBarOption({ x, xKind, unit, series, totals, totalLabel }, ctx),
    [x, xKind, unit, series, totals, totalLabel, ctx],
  );
  return (
    <ChartFrame
      title={title}
      summary={describeSeries({ x, xKind, unit, series }, ctx.f, t)}
      legend={series.map((s) => ({ key: s.key, name: s.name, color: s.color, shape: "bar" as const }))}
      empty={x.length === 0 || series.every((s) => s.values.every((v) => v === null))}
      table={{
        head: [t("charts.date"), ...series.map((s) => s.name), ...(totals ? [totalLabel] : [])],
        rows: x.map((value, i) => [
          xText(xKind, value, ctx.f),
          ...series.map((s) => valueText(unit, s.values[i] ?? null, ctx.f)),
          ...(totals ? [valueText(unit, totals[i] ?? null, ctx.f)] : []),
        ]),
      }}
    >
      <EChart option={option} height={height} />
    </ChartFrame>
  );
}
