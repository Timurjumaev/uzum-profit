// Ustun + chiziq, bitta o'q (04 §5, §5.1): kunlik tushum (ustun) va sof foyda (chiziq) kabi. Annotatsiyalar:
// `bands` — davr belgisi (soya), sinxron uzilgan kunlar (shtrix).
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { describeSeries } from "./describe";
import { EChart } from "./EChart";
import { ChartFrame } from "./ChartFrame";
import { lineBarOption, valueText, xText } from "./options";
import type { Band, LegendItem, SeriesInput, Unit, XKind } from "./types";
import { useChartCtx } from "./useChartCtx";

export type LineBarChartProps = {
  title: string;
  /** Kategoriyalar: ISO sana ("2026-10-01"), oy ("2026-10-01") yoki matn. */
  x: string[];
  xKind?: XKind;
  unit?: Unit;
  series: SeriesInput[];
  bands?: Band[];
  height?: number;
};

export function LineBarChart({ title, x, xKind = "day", unit = "money", series, bands = [], height }: LineBarChartProps) {
  const { t } = useTranslation();
  const ctx = useChartCtx();
  const option = useMemo(() => lineBarOption({ x, xKind, unit, series, bands }, ctx), [x, xKind, unit, series, bands, ctx]);
  const legend: LegendItem[] = [
    ...series.map((s) => ({ key: s.key, name: s.name, color: s.color, shape: s.kind === "line" ? ("line" as const) : ("bar" as const) })),
    ...bands.map((b, i) => ({ key: `band-${i}`, name: b.label, color: "other" as const, shape: b.kind })),
  ];
  return (
    <ChartFrame
      title={title}
      summary={describeSeries({ x, xKind, unit, series }, ctx.f, t)}
      legend={legend}
      empty={x.length === 0 || series.every((s) => s.values.every((v) => v === null))}
      table={{
        head: [t("charts.date"), ...series.map((s) => s.name)],
        rows: x.map((value, i) => [xText(xKind, value, ctx.f), ...series.map((s) => valueText(unit, s.values[i] ?? null, ctx.f))]),
      }}
    >
      <EChart option={option} height={height} />
    </ChartFrame>
  );
}
