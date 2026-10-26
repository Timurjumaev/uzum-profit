// Issiqlik xaritasi (hafta kuni × soat) va kalendar issiqlik xaritasi (kunlik) — ketma-ket bitta ko'k shkala
// (04 §4.3); shkala legendasi grafik ostida, aniq qiymat — tooltip va jadvalda.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { extremes, hourLabel, monthNames, weekdayNames, weekdayNamesSunFirst } from "./describe";
import { EChart } from "./EChart";
import { ChartFrame, type ChartScale } from "./ChartFrame";
import { calendarHeatmapOption, heatmapOption, num, valueText } from "./options";
import type { Unit, Value } from "./types";
import { useChartCtx } from "./useChartCtx";

export type HeatmapChartProps = {
  title: string;
  /** 7 qator (dushanba … yakshanba) × 24 soat. */
  values: Value[][];
  unit?: Unit;
  /** Tooltip'dagi qiymat nomi ("Buyurtmalar"). */
  valueLabel: string;
  height?: number;
};

function useScale(): ChartScale {
  const { t } = useTranslation();
  const { palette } = useChartCtx();
  return { from: palette.sequential[0], to: palette.sequential[1], minLabel: t("charts.scale.less"), maxLabel: t("charts.scale.more") };
}

export function HeatmapChart({ title, values, unit = "count", valueLabel, height = 260 }: HeatmapChartProps) {
  const { t } = useTranslation();
  const ctx = useChartCtx();
  const scale = useScale();
  const weekdays = useMemo(() => weekdayNames(ctx.f), [ctx.f]);
  const option = useMemo(
    () => heatmapOption({ values, weekdays, hourLabel, unit, valueLabel }, ctx),
    [values, weekdays, unit, valueLabel, ctx],
  );
  const flat = values.flat();
  const peak = extremes(flat);
  const summary = peak
    ? t("charts.summary.peak", {
        weekday: weekdays[Math.floor(peak.max / 24)],
        hour: hourLabel(peak.max % 24),
        value: valueText(unit, flat[peak.max], ctx.f),
      })
    : "";
  return (
    <ChartFrame
      title={title}
      summary={summary}
      scale={scale}
      empty={flat.every((v) => num(v) === null)}
      table={{
        head: [t("charts.weekday"), ...Array.from({ length: 24 }, (_, h) => hourLabel(h))],
        rows: values.map((row, d) => [weekdays[d], ...row.map((v) => valueText(unit, v, ctx.f))]),
      }}
    >
      <EChart option={option} height={height} />
    </ChartFrame>
  );
}

export type CalendarHeatmapProps = {
  title: string;
  days: Array<{ date: string; value: Value }>;
  unit?: Unit;
  valueLabel: string;
  height?: number;
};

export function CalendarHeatmap({ title, days, unit = "money", valueLabel, height = 200 }: CalendarHeatmapProps) {
  const { t } = useTranslation();
  const ctx = useChartCtx();
  const scale = useScale();
  const sorted = useMemo(() => [...days].sort((a, b) => a.date.localeCompare(b.date)), [days]);
  const range: [string, string] = [sorted[0]?.date ?? "", sorted[sorted.length - 1]?.date ?? ""];
  const option = useMemo(
    () =>
      calendarHeatmapOption(
        { days: sorted, range, weekdaysSunFirst: weekdayNamesSunFirst(ctx.f), months: monthNames(ctx.f), unit, valueLabel },
        ctx,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sorted, range[0], range[1], unit, valueLabel, ctx],
  );
  const peak = extremes(sorted.map((d) => d.value));
  const summary = peak
    ? t("charts.summary.series", {
        name: valueLabel,
        max: valueText(unit, sorted[peak.max].value, ctx.f),
        at: ctx.f.day(sorted[peak.max].date),
        min: valueText(unit, sorted[peak.min].value, ctx.f),
        atMin: ctx.f.day(sorted[peak.min].date),
      })
    : "";
  return (
    <ChartFrame
      title={title}
      summary={`${t("charts.summary.points", { count: sorted.length })} ${summary}`}
      scale={scale}
      empty={sorted.every((d) => num(d.value) === null)}
      table={{ head: [t("charts.date"), valueLabel], rows: sorted.map((d) => [ctx.f.day(d.date), valueText(unit, d.value, ctx.f)]) }}
    >
      <EChart option={option} height={height} />
    </ChartFrame>
  );
}
