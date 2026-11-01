// ECharts parametrlari quruvchilari (04 §5.1): sof funksiyalar (ma'lumot + palitra + formatlovchi → parametr), shuning
// uchun jsdom'da ham sinaladi. Qoidalar: bitta o'q; ustun ≤ 24 px, uchi 4 px yumaloq, orasida 2 px fon; chiziq 2 px,
// marker ≥ 8 px 2 px fon halqasi bilan; to'r — hairline, yaxlit; o'q raqamlari ixcham; yorliq/qiymat matn tokenida.
import type { EChartsCoreOption } from "../../lib/echarts";
import type { Formatter } from "../../lib/format";
import { colorOf, type Palette } from "./palette";
import { tooltipBase, tooltipHtml, type TooltipRow } from "./tooltip";
import type { Band, SeriesInput, Unit, Value, XKind } from "./types";

export type Ctx = { f: Formatter; palette: Palette; /** false — `prefers-reduced-motion`. */ motion: boolean };

const BAR_MAX = 24;
const MARKER = 8;
/** Nuqta soni shundan oshsa markerlar faqat hover'da (31 kunlik grafik markerlardan to'lib ketmasin). */
const MARKERS_UP_TO = 14;
/** Seriya soni shundan oshmasa chiziq oxirida to'g'ridan-to'g'ri yorliq (04 §5.1). */
const DIRECT_LABELS_UP_TO = 4;

export const num = (v: Value): number | null => {
  if (v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export function valueText(unit: Unit, v: Value, f: Formatter): string {
  if (v === null) return "—";
  return unit === "money" ? f.money(v) : f.number(v);
}

export function xText(kind: XKind, x: string, f: Formatter): string {
  return kind === "day" ? f.day(x) : kind === "month" ? f.month(x) : x;
}

function axes(ctx: Ctx, x: string[], xKind: XKind, nonNegative: boolean) {
  const { f, palette } = ctx;
  const label = { color: palette.textSecondary, fontFamily: palette.font, fontSize: 12 };
  return {
    xAxis: {
      type: "category",
      data: x,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: palette.hairline } },
      axisLabel: { ...label, hideOverlap: true, formatter: (value: string) => xText(xKind, value, f) },
    },
    yAxis: {
      type: "value",
      min: nonNegative ? 0 : undefined,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: palette.hairline, type: "solid", width: 1 } },
      axisLabel: { ...label, formatter: (value: number) => f.compact(Math.round(value)) },
    },
  };
}

// ECharts 6: o'q yorliqlari standart bo'yicha maydon ichida (`containLabel` eskirgan).
const grid = (right = 16) => ({ left: 8, right, top: 16, bottom: 8 });

const base = (ctx: Ctx) => ({
  animation: ctx.motion,
  textStyle: { fontFamily: ctx.palette.font },
  backgroundColor: "transparent",
});

function bandAreas(bands: Band[], palette: Palette) {
  return {
    silent: true,
    data: bands.map((band) => [
      {
        xAxis: band.from,
        // `shade` — to'ldirilgan soya; `hatch` — punktir ramkali bo'sh maydon (markArea `decal` ni qo'llamaydi).
        itemStyle:
          band.kind === "shade"
            ? { color: palette.raised, opacity: 0.9 }
            : { color: "transparent", borderColor: palette.muted, borderWidth: 1, borderType: "dashed" },
      },
      { xAxis: band.to },
    ]),
  };
}

/** Ustun va/yoki chiziq, bitta o'q (so'm yoki dona — ikkalasi bir grafikda emas). */
export function lineBarOption(
  input: { x: string[]; xKind: XKind; unit: Unit; series: SeriesInput[]; bands?: Band[] },
  ctx: Ctx,
): EChartsCoreOption {
  const { x, xKind, unit, series, bands = [] } = input;
  const { f, palette } = ctx;
  const hasLine = series.some((s) => s.kind === "line");
  const direct = series.length <= DIRECT_LABELS_UP_TO && hasLine;
  const nonNegative = series.every((s) => s.values.every((v) => (num(v) ?? 0) >= 0));
  return {
    ...base(ctx),
    grid: grid(direct ? 72 : 16),
    ...axes(ctx, x, xKind, nonNegative),
    tooltip: {
      ...tooltipBase(palette),
      trigger: "axis",
      // Chiziqda crosshair, faqat ustunda — shu ustun (04 §5.1).
      axisPointer: hasLine
        ? { type: "line", lineStyle: { color: palette.muted, width: 1 } }
        : { type: "shadow", shadowStyle: { color: palette.raised, opacity: 0.6 } },
      formatter: (params: unknown) => {
        const index = (params as Array<{ dataIndex: number }>)[0]?.dataIndex ?? 0;
        const rows: TooltipRow[] = series.map((s) => ({
          name: s.name,
          value: valueText(unit, s.values[index] ?? null, f),
          color: colorOf(palette, s.color),
          shape: s.kind === "line" ? "line" : "bar",
        }));
        return tooltipHtml(xText(xKind, x[index], f), rows);
      },
    },
    series: series.map((s, i) => {
      const color = colorOf(palette, s.color);
      const markArea = i === 0 && bands.length > 0 ? bandAreas(bands, palette) : undefined;
      if (s.kind === "line") {
        return {
          name: s.name,
          type: "line",
          data: s.values.map(num),
          color,
          lineStyle: { width: 2, color },
          symbol: "circle",
          symbolSize: MARKER,
          showSymbol: x.length <= MARKERS_UP_TO,
          itemStyle: { color, borderColor: palette.surface, borderWidth: 2 },
          emphasis: { focus: "series", scale: false },
          endLabel: direct
            ? { show: true, formatter: s.name, color: palette.textSecondary, fontFamily: palette.font, fontSize: 12 }
            : undefined,
          labelLayout: { hideOverlap: true },
          markArea,
        };
      }
      // Qatlamli ustunda faqat eng yuqori qatlamning uchi yumaloq (pastkilari to'g'ri).
      const below = s.stack !== undefined && series.slice(i + 1).some((o) => o.stack === s.stack && o.kind !== "line");
      return {
        name: s.name,
        type: "bar",
        stack: s.stack,
        data: s.values.map((v) => {
          const n = num(v);
          return n !== null && n < 0
            ? { value: n, itemStyle: { borderRadius: [0, 0, 4, 4] } }
            : n;
        }),
        color,
        barMaxWidth: BAR_MAX,
        itemStyle: { color, borderRadius: below ? 0 : [4, 4, 0, 0], borderColor: palette.surface, borderWidth: 1 },
        emphasis: { focus: "none" },
        markArea,
      };
    }),
  };
}

/** Qatlamli ustun (masalan, xarajatlar tarkibi). `totals` — API'dan tayyor jami (tooltip'da "Jami"). */
export function stackedBarOption(
  input: { x: string[]; xKind: XKind; unit: Unit; series: SeriesInput[]; totals?: Value[]; totalLabel: string },
  ctx: Ctx,
): EChartsCoreOption {
  const { x, xKind, unit, series, totals, totalLabel } = input;
  const { f, palette } = ctx;
  // Eng yuqori (oxirgi nol bo'lmagan) segmentning uchi yumaloq, qolganlariniki — to'g'ri.
  const topSeries = x.map((_, i) => {
    for (let s = series.length - 1; s >= 0; s--) if ((num(series[s].values[i]) ?? 0) > 0) return s;
    return -1;
  });
  return {
    ...base(ctx),
    grid: grid(),
    ...axes(ctx, x, xKind, true),
    tooltip: {
      ...tooltipBase(palette),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: palette.raised, opacity: 0.6 } },
      formatter: (params: unknown) => {
        const index = (params as Array<{ dataIndex: number }>)[0]?.dataIndex ?? 0;
        const rows: TooltipRow[] = series.map((s) => ({
          name: s.name,
          value: valueText(unit, s.values[index] ?? null, f),
          color: colorOf(palette, s.color),
          shape: "bar",
        }));
        if (totals) rows.push({ name: totalLabel, value: valueText(unit, totals[index] ?? null, f) });
        return tooltipHtml(xText(xKind, x[index], f), rows);
      },
    },
    series: series.map((s, si) => {
      const color = colorOf(palette, s.color);
      return {
        name: s.name,
        type: "bar",
        stack: "total",
        data: s.values.map((v, i) => ({
          value: num(v),
          itemStyle: { borderRadius: topSeries[i] === si ? [4, 4, 0, 0] : 0 },
        })),
        color,
        barMaxWidth: BAR_MAX,
        itemStyle: { color, borderColor: palette.surface, borderWidth: 1 },
        emphasis: { focus: "none" },
      };
    }),
  };
}

export type WaterfallStep = {
  key: string;
  label: string;
  /** API qiymati: qo'shiluvchi — musbat, ayriluvchi — manfiy ("-37284000.00"), yakuniy — oraliq/yakuniy summa. */
  amount: string;
  kind: "add" | "subtract" | "total";
};

/** Chizish geometriyasi (faqat joylashuv — ko'rsatiladigan raqam `amount` satridan): [boshlanish, tugash, daraja]. */
export function waterfallGeometry(steps: WaterfallStep[]): Array<[number, number, number]> {
  let level = 0;
  return steps.map((step) => {
    const amount = Number(step.amount);
    if (step.kind === "total") {
      level = amount;
      return [0, amount, level];
    }
    const start = level;
    level += amount;
    return [start, level, level];
  });
}

/** Sharshara (`compact` — tor ekran): qo'shiluvchi — slot 1, ayriluvchi — slot 8, yakuniy — siyoh; ustunlar orasida bog'lovchi chiziq. */
export function waterfallOption(input: { steps: WaterfallStep[]; unit?: Unit; compact?: boolean }, ctx: Ctx): EChartsCoreOption {
  const { steps, unit = "money", compact = false } = input;
  const { f, palette } = ctx;
  const geometry = waterfallGeometry(steps);
  const fill = (kind: WaterfallStep["kind"]) => (kind === "add" ? palette.add : kind === "subtract" ? palette.subtract : palette.ink);
  const axis = axes(ctx, steps.map((s) => s.label), "text", false);
  return {
    ...base(ctx),
    grid: { ...grid(), bottom: 24 },
    xAxis: {
      ...axis.xAxis,
      // Tor ekranda yorliqlar sig'maydi — qiya yoziladi; keng ekranda ikki qatorga bo'linadi.
      axisLabel: {
        ...axis.xAxis.axisLabel,
        formatter: (v: string) => v,
        interval: 0,
        hideOverlap: false,
        ...(compact ? { rotate: 40 } : { width: 72, overflow: "break" }),
      },
    },
    yAxis: axis.yAxis,
    tooltip: {
      ...tooltipBase(palette),
      trigger: "item",
      formatter: (params: unknown) => {
        const step = steps[(params as { dataIndex: number }).dataIndex];
        return tooltipHtml(step.label, [{ name: "", value: valueText(unit, step.amount, f), color: fill(step.kind), shape: "bar" }]);
      },
    },
    series: [
      {
        type: "custom",
        data: steps.map((step, i) => ({
          value: [i, ...geometry[i]],
          itemStyle: { color: fill(step.kind) },
        })),
        renderItem: (_: unknown, api: CustomApi) => {
          const i = api.value(0);
          const [x0, y0] = api.coord([i, api.value(1)]);
          const [, y1] = api.coord([i, api.value(2)]);
          const width = Math.min(api.size([1, 0])[0] * 0.6, BAR_MAX);
          const [nextX, levelY] = api.coord([i + 1, api.value(3)]);
          const last = i === steps.length - 1;
          return {
            type: "group",
            children: [
              {
                type: "rect",
                shape: { x: x0 - width / 2, y: Math.min(y0, y1), width, height: Math.max(Math.abs(y1 - y0), 1), r: [4, 4, 0, 0] },
                style: { fill: fill(steps[i].kind) }, // `api.style()` ECharts 6 da eskirgan
              },
              ...(last
                ? []
                : [
                    {
                      type: "line",
                      shape: { x1: x0 + width / 2, y1: levelY, x2: nextX - width / 2, y2: levelY },
                      style: { stroke: palette.muted, lineWidth: 1 },
                    },
                  ]),
            ],
          };
        },
        encode: { x: 0, y: [1, 2] },
      },
    ],
  };
}

/** `renderItem` ga ECharts beradigan yordamchi (faqat ishlatiladigan qismi). */
type CustomApi = {
  value: (dim: number) => number;
  coord: (point: [number, number]) => [number, number];
  size: (size: [number, number]) => [number, number];
};

const sequentialVisual = (palette: Palette, min: number, max: number) => ({
  type: "continuous",
  show: false,
  min,
  max: max === min ? min + 1 : max,
  inRange: { color: palette.sequential },
});

/** Issiqlik xaritasi: hafta kuni (dushanba — tepada) × soat; qiymatlar [7][24]. */
export function heatmapOption(
  input: { values: Value[][]; weekdays: string[]; hourLabel: (hour: number) => string; unit: Unit; valueLabel: string },
  ctx: Ctx,
): EChartsCoreOption {
  const { values, weekdays, hourLabel, unit, valueLabel } = input;
  const { f, palette } = ctx;
  const data: Array<[number, number, number]> = [];
  values.forEach((row, d) => row.forEach((v, h) => num(v) !== null && data.push([h, d, num(v)!])));
  const numbers = data.map((d) => d[2]);
  const label = { color: palette.textSecondary, fontFamily: palette.font, fontSize: 12 };
  return {
    ...base(ctx),
    grid: { left: 8, right: 8, top: 8, bottom: 8 },
    xAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, h) => String(h)),
      axisTick: { show: false },
      axisLine: { show: false },
      splitArea: { show: false },
      axisLabel: { ...label, hideOverlap: true, formatter: (h: string) => hourLabel(Number(h)) },
    },
    yAxis: { type: "category", data: weekdays, inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: label },
    visualMap: sequentialVisual(palette, Math.min(...numbers, 0), Math.max(...numbers, 0)),
    tooltip: {
      ...tooltipBase(palette),
      trigger: "item",
      formatter: (params: unknown) => {
        const [h, d] = (params as { value: [number, number, number] }).value;
        const raw = values[d]?.[h] ?? null;
        return tooltipHtml(`${weekdays[d]}, ${hourLabel(h)}`, [{ name: valueLabel, value: valueText(unit, raw, f) }]);
      },
    },
    series: [
      {
        type: "heatmap",
        data,
        itemStyle: { borderColor: palette.surface, borderWidth: 2, borderRadius: 2 },
        emphasis: { itemStyle: { borderColor: palette.ink, borderWidth: 2 } },
      },
    ],
  };
}

/** Kalendar issiqlik xaritasi (kunlik): `days` — sana (YYYY-MM-DD) va qiymat. */
export function calendarHeatmapOption(
  input: {
    days: Array<{ date: string; value: Value }>;
    range: [string, string];
    /** Yakshanbadan boshlanadi (ECharts tartibi), `firstDay: 1` bilan ko'rinish dushanbadan. */
    weekdaysSunFirst: string[];
    months: string[];
    unit: Unit;
    valueLabel: string;
  },
  ctx: Ctx,
): EChartsCoreOption {
  const { days, range, weekdaysSunFirst, months, unit, valueLabel } = input;
  const { f, palette } = ctx;
  const known = days.filter((d) => num(d.value) !== null);
  const numbers = known.map((d) => num(d.value)!);
  const rawByDate = new Map(days.map((d) => [d.date, d.value]));
  const label = { color: palette.textSecondary, fontFamily: palette.font, fontSize: 12 };
  return {
    ...base(ctx),
    tooltip: {
      ...tooltipBase(palette),
      trigger: "item",
      formatter: (params: unknown) => {
        const date = (params as { value: [string, number] }).value[0];
        return tooltipHtml(f.day(date), [{ name: valueLabel, value: valueText(unit, rawByDate.get(date) ?? null, f) }]);
      },
    },
    visualMap: sequentialVisual(palette, Math.min(...numbers, 0), Math.max(...numbers, 0)),
    calendar: {
      range,
      orient: "horizontal",
      top: 24,
      left: 32,
      right: 8,
      bottom: 8,
      cellSize: ["auto", 16],
      splitLine: { show: false },
      yearLabel: { show: false },
      itemStyle: { color: palette.raised, borderColor: palette.surface, borderWidth: 2 },
      dayLabel: { firstDay: 1, nameMap: weekdaysSunFirst, ...label },
      monthLabel: { nameMap: months, ...label },
    },
    series: [
      {
        type: "heatmap",
        coordinateSystem: "calendar",
        data: known.map((d) => [d.date, num(d.value)]),
        itemStyle: { borderRadius: 2 },
        emphasis: { itemStyle: { borderColor: palette.ink, borderWidth: 2 } },
      },
    ],
  };
}
