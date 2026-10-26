// Grafik komponentlari: ramka (legenda, "Jadval" ko'rinishi, bo'sh holat, aria), ECharts bilan hayot sikli (yuklash,
// mavzu almashuvi, o'lcham, dispose, yuklanmasa qayta urinish). ECharts soxta — chizish `echarts.smoke.test.tsx` da.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadEcharts } from "../../lib/echarts";
import { formatterFor } from "../../lib/format";
import { createI18n, type Lang } from "../../lib/i18n";
import { applyTheme } from "../../lib/theme";
import { CalendarHeatmap, HeatmapChart, LineBarChart, StackedBarChart, WaterfallChart } from ".";

vi.mock("../../lib/echarts", () => ({ loadEcharts: vi.fn() }));

type Fake = { setOption: ReturnType<typeof vi.fn>; resize: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn> };
let instances: Fake[] = [];
let init: ReturnType<typeof vi.fn>;

const f = formatterFor("uz-Latn");
const wrap = (node: ReactNode, lang: Lang = "uz-Latn") => render(<I18nextProvider i18n={createI18n(lang)}>{node}</I18nextProvider>);

function matchMedia(matching: string[] = []) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: matching.some((m) => query.includes(m)),
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  instances = [];
  init = vi.fn(() => {
    const chart: Fake = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
    instances.push(chart);
    return chart;
  });
  vi.mocked(loadEcharts).mockResolvedValue({ init } as never);
  matchMedia();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

const X = ["2026-10-01", "2026-10-02", "2026-10-03"];
const SERIES = [
  { key: "revenue", name: "Tushum", color: 1, values: ["1000000", "2500000", null] },
  { key: "profit", name: "Sof foyda", color: "ink" as const, kind: "line" as const, values: ["300000", "-50000", "700000"] },
];
const lineBar = (props: Partial<Parameters<typeof LineBarChart>[0]> = {}) => (
  <LineBarChart title="Kunlik tushum" x={X} series={SERIES} {...props} />
);
const option = (instance = 0, call = 0) => instances[instance].setOption.mock.calls[call][0] as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
/** Qator kataklari matni (NBSP saqlanadi — testing-library qidiruvi uni oddiy bo'sh joyga aylantiradi). */
const cells = (row: HTMLElement) => [...row.querySelectorAll("th,td")].map((c) => c.textContent);
const bodyRows = (table: HTMLElement) => within(table).getAllByRole("row").slice(1).map(cells);
const ready = () => waitFor(() => expect(instances[0]?.setOption).toHaveBeenCalled());

describe("LineBarChart ramkasi", () => {
  it("sarlavha, legenda (≥ 2 seriya + annotatsiyalar), matnli tavsif", async () => {
    wrap(
      lineBar({
        bands: [
          { from: "2026-10-01", to: "2026-10-02", kind: "shade", label: "Uzum bepul logistika" },
          { from: "2026-10-03", to: "2026-10-03", kind: "hatch", label: "Sinxron uzilgan" },
        ],
      }),
    );
    await ready();
    expect(screen.getByRole("heading", { name: "Kunlik tushum" })).toBeTruthy();
    const legend = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(legend).toEqual(["Tushum", "Sof foyda", "Uzum bepul logistika", "Sinxron uzilgan"]);
    const img = screen.getByRole("img");
    const label = img.getAttribute("aria-label")!;
    expect(label).toContain("Kunlik tushum");
    expect(label).toContain("3 nuqta");
    expect(label).toContain(`Tushum: eng yuqori ${f.money("2500000")} (${f.day("2026-10-02")})`);
    expect(label).toContain(`Sof foyda: eng yuqori ${f.money("700000")}`);
  });

  it("bitta seriyada legenda yo'q", async () => {
    wrap(lineBar({ series: [SERIES[0]] }));
    await ready();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("ECharts SVG renderer bilan ishga tushadi; parametr to'liq almashtiriladi", async () => {
    wrap(lineBar());
    await ready();
    expect(init).toHaveBeenCalledOnce();
    expect(init.mock.calls[0][2]).toEqual({ renderer: "svg" });
    expect(instances[0].setOption).toHaveBeenCalledOnce();
    expect(instances[0].setOption.mock.calls[0][1]).toEqual({ notMerge: true });
    expect(option().series).toHaveLength(2);
  });

  it("'Jadval' ko'rinishi: bir xil ma'lumot matnda (aniq qiymatlar, null — tire), grafik olib tashlanadi", async () => {
    wrap(lineBar());
    await ready();
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    expect(screen.queryByRole("img")).toBeNull();
    expect(instances[0].dispose).toHaveBeenCalledOnce();
    const table = screen.getByRole("table", { name: "Kunlik tushum" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Sana", "Tushum", "Sof foyda"]);
    expect(bodyRows(table)).toEqual([
      [f.day("2026-10-01"), f.money("1000000"), f.money("300000")],
      [f.day("2026-10-02"), f.money("2500000"), f.money("-50000")],
      [f.day("2026-10-03"), "—", f.money("700000")],
    ]);
    fireEvent.click(screen.getByRole("radio", { name: "Grafik" }));
    await waitFor(() => expect(instances).toHaveLength(2));
    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("bo'sh ma'lumot: bo'sh holat, almashtirgich va ECharts yuklanmaydi", () => {
    wrap(<LineBarChart title="Tushum" x={[]} series={[]} />);
    expect(screen.getByText("Bu davrda maʼlumot yoʻq")).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(loadEcharts).not.toHaveBeenCalled();
    cleanup();
    wrap(<LineBarChart title="Tushum" x={X} series={[{ key: "a", name: "A", color: 1, values: [null, null, null] }]} />);
    expect(screen.getByText("Bu davrda maʼlumot yoʻq")).toBeTruthy();
  });

  it("ruscha", async () => {
    wrap(lineBar(), "ru");
    await ready();
    expect(screen.getByRole("radio", { name: "Таблица" })).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Точек: 3");
  });
});

describe("hayot sikli", () => {
  it("yuklanguncha skelet; yuklangach yo'qoladi", async () => {
    let resolve!: (v: never) => void;
    vi.mocked(loadEcharts).mockReturnValue(new Promise((r) => (resolve = r as never)));
    wrap(lineBar());
    expect(screen.getByRole("status", { name: "Grafik yuklanmoqda" })).toBeTruthy();
    await act(async () => resolve({ init } as never));
    expect(screen.queryByRole("status", { name: "Grafik yuklanmoqda" })).toBeNull();
    expect(init).toHaveBeenCalledOnce();
  });

  it("mavzu almashsa grafik yangi ranglar bilan qayta chiziladi", async () => {
    wrap(lineBar());
    await ready();
    const light = option().series[0].color;
    act(() => void applyTheme("dark"));
    await waitFor(() => expect(instances[0].setOption).toHaveBeenCalledTimes(2));
    expect(option(0, 1).series[0].color).not.toBe(light);
    expect(option(0, 1).series[1].color).toBe("#EEF0F4"); // siyoh — qorong'ida oq
  });

  it("til almashsa (qayta render) ham parametr yangilanadi, yangi ECharts yaratilmaydi", async () => {
    const { rerender } = wrap(lineBar());
    await ready();
    rerender(
      <I18nextProvider i18n={createI18n("uz-Latn")}>
        {lineBar({ x: ["2026-10-04", "2026-10-05", "2026-10-06"] })}
      </I18nextProvider>,
    );
    await waitFor(() => expect(instances[0].setOption).toHaveBeenCalledTimes(2));
    expect(init).toHaveBeenCalledOnce();
    expect(option(0, 1).xAxis.data[0]).toBe("2026-10-04");
  });

  it("o'lcham o'zgarsa resize; olib tashlansa dispose va kuzatuvchi to'xtaydi", async () => {
    const disconnect = vi.fn();
    let callback!: () => void;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          callback = cb;
        }
        observe() {}
        disconnect = disconnect;
      },
    );
    const { unmount } = wrap(lineBar());
    await ready();
    callback();
    expect(instances[0].resize).toHaveBeenCalledOnce();
    unmount();
    expect(instances[0].dispose).toHaveBeenCalledOnce();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("yuklash tugamasdan olib tashlansa ECharts yaratilmaydi", async () => {
    let resolve!: (v: never) => void;
    vi.mocked(loadEcharts).mockReturnValue(new Promise((r) => (resolve = r as never)));
    const { unmount } = wrap(lineBar());
    unmount();
    await act(async () => resolve({ init } as never));
    expect(init).not.toHaveBeenCalled();
  });

  it("yuklanmasa (tarmoq) — xabar va 'Qayta urinish'; jadval ko'rinishi ishlayveradi", async () => {
    vi.mocked(loadEcharts).mockRejectedValueOnce(new Error("chunk"));
    wrap(lineBar());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Grafik yuklanmadi");
    fireEvent.click(within(alert).getByRole("button", { name: "Qayta urinish" }));
    await ready();
    expect(init).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).toBeNull();
    cleanup();

    vi.mocked(loadEcharts).mockRejectedValueOnce(new Error("chunk"));
    wrap(lineBar());
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    expect(screen.getByRole("table")).toBeTruthy();
  });

  it("prefers-reduced-motion — animatsiya o'chiq", async () => {
    matchMedia(["prefers-reduced-motion"]);
    wrap(lineBar());
    await ready();
    expect(option().animation).toBe(false);
  });
});

describe("boshqa grafiklar", () => {
  it("StackedBarChart: legenda seriyalar, jadvalda API'dan kelgan 'Jami'", async () => {
    wrap(
      <StackedBarChart
        title="Xarajatlar tarkibi"
        x={["2026-09-01", "2026-10-01"]}
        series={[
          { key: "c", name: "Komissiya", color: 2, values: ["100", "200"] },
          { key: "l", name: "Logistika", color: 3, values: ["50", "60"] },
        ]}
        totals={["150", "260"]}
      />,
    );
    await ready();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Komissiya", "Logistika"]);
    expect(option().series.every((s: { stack: string }) => s.stack === "total")).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Sana", "Komissiya", "Logistika", "Jami"]);
    expect(bodyRows(table)).toEqual([
      [f.month("2026-09-01"), f.money("100"), f.money("50"), f.money("150")],
      [f.month("2026-10-01"), f.money("200"), f.money("60"), f.money("260")],
    ]);
  });

  it("WaterfallChart: legenda (qo'shiladi, ayriladi, yakun), yakuniy qadam tavsifda, jadval", async () => {
    const steps = [
      { key: "r", label: "Tushum", amount: "186420000.00", kind: "total" as const },
      { key: "c", label: "Komissiya", amount: "-37284000.00", kind: "subtract" as const },
      { key: "n", label: "Sof foyda", amount: "149136000.00", kind: "total" as const },
    ];
    wrap(<WaterfallChart title="Sharshara" steps={steps} />);
    await ready();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Qoʻshiladi", "Ayriladi", "Yakun"]);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain(`3 qadam; yakun: Sof foyda ${f.money("149136000.00")}`);
    expect(option().series[0].type).toBe("custom");
    expect(option().xAxis.axisLabel.rotate).toBeUndefined();
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    expect(bodyRows(screen.getByRole("table")).map((r) => r[1])).toEqual([f.money("186420000.00"), f.money("-37284000.00"), f.money("149136000.00")]);
  });

  it("WaterfallChart tor ekranda qiya yorliqlar bilan", async () => {
    matchMedia(["max-width: 639px"]);
    wrap(<WaterfallChart title="Sharshara" steps={[{ key: "r", label: "Tushum", amount: "10", kind: "total" }]} />);
    await ready();
    expect(option().xAxis.axisLabel.rotate).toBe(40);
  });

  it("HeatmapChart: shkala legendasi, eng yuqori katak tavsifda, jadval 7 × 24", async () => {
    const values = Array.from({ length: 7 }, (_, d) => Array.from({ length: 24 }, (_, h) => (d === 4 && h === 15 ? "42" : "1")));
    wrap(<HeatmapChart title="Buyurtmalar" values={values} valueLabel="Buyurtmalar" />);
    await ready();
    expect(screen.getByText("kam")).toBeTruthy();
    expect(screen.getByText("koʻp")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Eng yuqori: Ju, 15:00 — 42");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader")).toHaveLength(25);
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    expect(within(table).getByRole("rowheader", { name: "Ju" })).toBeTruthy();
  });

  it("CalendarHeatmap: tartiblanadi, oraliq birinchi–oxirgi kun, jadval sanalar bo'yicha", async () => {
    const days = [
      { date: "2026-10-03", value: "300" },
      { date: "2026-10-01", value: "100" },
      { date: "2026-10-02", value: null },
    ];
    wrap(<CalendarHeatmap title="Kalendar" days={days} valueLabel="Tushum" />);
    await ready();
    expect(option().calendar.range).toEqual(["2026-10-01", "2026-10-03"]);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("3 nuqta");
    fireEvent.click(screen.getByRole("radio", { name: "Jadval" }));
    expect(bodyRows(screen.getByRole("table"))).toEqual([
      [f.day("2026-10-01"), f.money("100")],
      [f.day("2026-10-02"), "—"],
      [f.day("2026-10-03"), f.money("300")],
    ]);
  });
});

describe("kirish imkoniyati (axe-core: jiddiy xato 0)", () => {
  it("grafik va jadval ko'rinishlari", async () => {
    const values = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => "3"));
    wrap(
      <>
        {lineBar()}
        <StackedBarChart title="Tarkib" x={X} series={SERIES.map((s, i) => ({ ...s, kind: undefined, color: i + 2 }))} />
        <WaterfallChart title="Sharshara" steps={[{ key: "r", label: "Tushum", amount: "10", kind: "total" }]} />
        <HeatmapChart title="Issiqlik" values={values} valueLabel="Buyurtmalar" />
        <CalendarHeatmap title="Kalendar" days={X.map((date) => ({ date, value: "5" }))} valueLabel="Tushum" />
      </>,
    );
    await waitFor(() => expect(instances).toHaveLength(5));
    const run = async () =>
      (await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } })).violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
    expect(await run()).toEqual([]);
    for (const radio of screen.getAllByRole("radio", { name: "Jadval" })) fireEvent.click(radio);
    expect(await run()).toEqual([]);
  }, 60_000);
});
