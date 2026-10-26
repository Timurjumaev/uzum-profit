// Sharshara (04 §5, §4.3): hisob varag'i qadamlari — qo'shiluvchi (slot 1), ayriluvchi (slot 8), yakuniy (siyoh).
// Qadam qiymatlari tayyor (API satrlari); grafik hisoblamaydi.
import { useMemo, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";

import { EChart } from "./EChart";
import { ChartFrame } from "./ChartFrame";
import { waterfallOption, valueText, type WaterfallStep } from "./options";
import type { LegendItem } from "./types";
import { useChartCtx } from "./useChartCtx";

const NARROW = "(max-width: 639px)";
const subscribeNarrow = (fn: () => void) => {
  const media = globalThis.matchMedia?.(NARROW);
  media?.addEventListener("change", fn);
  return () => media?.removeEventListener("change", fn);
};
const isNarrow = () => globalThis.matchMedia?.(NARROW).matches ?? false;

export type WaterfallChartProps = { title: string; steps: WaterfallStep[]; height?: number };

export function WaterfallChart({ title, steps, height = 320 }: WaterfallChartProps) {
  const { t } = useTranslation();
  const ctx = useChartCtx();
  const compact = useSyncExternalStore(subscribeNarrow, isNarrow, () => false);
  const option = useMemo(() => waterfallOption({ steps, compact }, ctx), [steps, compact, ctx]);
  const last = steps[steps.length - 1];
  const legend: LegendItem[] = [
    { key: "add", name: t("charts.waterfall.add"), color: 1, shape: "bar" },
    { key: "subtract", name: t("charts.waterfall.subtract"), color: 8, shape: "bar" },
    { key: "total", name: t("charts.waterfall.total"), color: "ink", shape: "bar" },
  ];
  return (
    <ChartFrame
      title={title}
      summary={last ? t("charts.summary.waterfall", { count: steps.length, label: last.label, value: valueText("money", last.amount, ctx.f) }) : ""}
      legend={legend}
      empty={steps.length === 0}
      table={{
        head: [t("charts.step"), t("charts.amount")],
        rows: steps.map((s) => [s.label, valueText("money", s.amount, ctx.f)]),
      }}
    >
      <EChart option={option} height={height} />
    </ChartFrame>
  );
}
