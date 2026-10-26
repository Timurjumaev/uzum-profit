// ECharts (ADR-005): faqat kerakli qismlar (`echarts/core`) va SVG renderer — boshlang'ich JS'ga tushmaydi
// (03 §9: ≤ 250 KB gzip); birinchi grafik so'ralganda alohida bo'lak yuklanadi. SVG: `aria`/matn tanlash va qorong'i
// rejimda aniq chiziqlar uchun, grafiklarimiz kichik (≤ bir necha yuz element).
import type { ECharts, EChartsCoreOption } from "echarts/core";

export type { ECharts, EChartsCoreOption };
export type EChartsApi = {
  init: (el: HTMLElement, theme?: string | object | null, opts?: { renderer: "svg" }) => ECharts;
};

let loading: Promise<EChartsApi> | null = null;

/** Bir marta yuklanadi; xato bo'lsa keyingi urinish qayta yuklaydi. */
export function loadEcharts(): Promise<EChartsApi> {
  loading ??= (async () => {
    const [core, charts, components, renderers] = await Promise.all([
      import("echarts/core"),
      import("echarts/charts"),
      import("echarts/components"),
      import("echarts/renderers"),
    ]);
    core.use([
      charts.BarChart,
      charts.LineChart,
      charts.HeatmapChart,
      charts.CustomChart,
      components.GridComponent,
      components.TooltipComponent,
      components.MarkAreaComponent,
      components.VisualMapComponent,
      components.CalendarComponent,
      renderers.SVGRenderer,
    ]);
    return core as unknown as EChartsApi;
  })().catch((error) => {
    loading = null;
    throw error;
  });
  return loading;
}
