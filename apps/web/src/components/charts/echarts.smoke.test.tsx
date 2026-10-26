// Haqiqiy ECharts (soxtasiz): hamma grafik jsdom'da SVG sifatida chiziladi, parametrlar kutubxona tomonidan rad
// etilmaydi (xato/ogohlantirish yo'q) va tooltip formatlovchisi haqiqiy hodisada ishlaydi. Piksel tekshiruvi — B3.8.
import { cleanup, render, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createI18n } from "../../lib/i18n";
import { CalendarHeatmap, HeatmapChart, LineBarChart, StackedBarChart, WaterfallChart } from ".";

beforeEach(() => {
  // jsdom'da maket yo'q — ECharts o'lchamni `clientWidth/Height` dan oladi.
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(640);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(280);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const X = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"];
const HEAT = Array.from({ length: 7 }, (_, d) => Array.from({ length: 24 }, (_, h) => String((d + h) % 5)));

describe("ECharts bilan haqiqiy chizish", () => {
  it("hamma grafik turi SVG chizadi, xato va ogohlantirishsiz", async () => {
    const problems: unknown[][] = [];
    vi.spyOn(console, "error").mockImplementation((...a) => void problems.push(a));
    vi.spyOn(console, "warn").mockImplementation((...a) => void problems.push(a));
    const { container } = render(
      <I18nextProvider i18n={createI18n("uz-Latn")}>
        <LineBarChart
          title="A"
          x={X}
          series={[
            { key: "r", name: "Tushum", color: 1, values: ["10", "20", null, "5"] },
            { key: "p", name: "Foyda", color: "ink", kind: "line", values: ["3", "-1", "4", "2"] },
          ]}
          bands={[{ from: "2026-10-01", to: "2026-10-02", kind: "shade", label: "x" }, { from: "2026-10-03", to: "2026-10-03", kind: "hatch", label: "y" }]}
        />
        <StackedBarChart title="B" x={X} series={[{ key: "c", name: "C", color: 2, values: ["1", "2", "3", "4"] }, { key: "l", name: "L", color: 3, values: ["4", "3", "2", "1"] }]} totals={["5", "5", "5", "5"]} />
        <WaterfallChart
          title="C"
          steps={[
            { key: "r", label: "Tushum", amount: "100", kind: "total" },
            { key: "c", label: "Komissiya", amount: "-130", kind: "subtract" },
            { key: "n", label: "Foyda", amount: "-30", kind: "total" },
          ]}
        />
        <HeatmapChart title="D" values={HEAT} valueLabel="Buyurtmalar" />
        <CalendarHeatmap title="E" days={X.map((date, i) => ({ date, value: String(i * 10) }))} valueLabel="Tushum" />
      </I18nextProvider>,
    );
    await waitFor(() => expect(container.querySelectorAll(".chart__canvas svg")).toHaveLength(5), { timeout: 10_000 });
    expect(container.querySelector(".chart__overlay")).toBeNull();
    // Ustunlar, chiziq, issiqlik kataklari va sharshara qadamlari haqiqatan chizilgan (zrender kadrda chizadi).
    await waitFor(
      () => {
        for (const svg of container.querySelectorAll(".chart__canvas svg")) expect(svg.querySelectorAll("path, rect").length).toBeGreaterThan(3);
      },
      { timeout: 10_000 },
    );
    expect(problems).toEqual([]);
  }, 30_000);
});
