// Grafik quruvchilari (04 §5.1 qoidalari kodda): sof funksiyalar — jsdom'da ECharts'siz sinaladi.
import { describe, expect, it } from "vitest";

import { formatterFor } from "../../lib/format";
import { chartRoles, chartSequential, chartSlots, colors } from "../../styles/tokens";
import { describeSeries, extremes, hourLabel, monthNames, weekdayNames, weekdayNamesSunFirst } from "./describe";
import {
  calendarHeatmapOption,
  heatmapOption,
  lineBarOption,
  num,
  stackedBarOption,
  valueText,
  waterfallGeometry,
  waterfallOption,
  xText,
  type Ctx,
  type WaterfallStep,
} from "./options";
import { chartPalette, colorOf, cssColor } from "./palette";
import { escapeHtml, tooltipHtml } from "./tooltip";

const f = formatterFor("uz-Latn");
const ctx = (over: Partial<Ctx> = {}): Ctx => ({ f, palette: chartPalette("light"), motion: true, ...over });
const NBSP = " ";

// ECharts parametrlari erkin shaklda — testda kerakli joyga qulay kirish uchun.
type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const opt = (o: unknown) => o as Any;

const X = ["2026-10-01", "2026-10-02", "2026-10-03"];
const REVENUE = { key: "revenue", name: "Tushum", color: 1, values: ["1000000.00", "2500000.50", null] };
const PROFIT = { key: "profit", name: "Sof foyda", color: "ink" as const, kind: "line" as const, values: ["300000", "-50000", "700000"] };

describe("palitra (04 §4.3)", () => {
  it("rang tokenlardan; qorong'i rejimda boshqa", () => {
    for (const theme of ["light", "dark"] as const) {
      const p = chartPalette(theme);
      expect(p.slots).toEqual(chartSlots[theme]);
      expect(p.ink).toBe(colors[theme]["text-primary"]);
      expect(p.surface).toBe(colors[theme]["bg-surface"]);
      expect(p.add).toBe(chartSlots[theme][chartRoles.revenue - 1]);
      expect(p.subtract).toBe(chartSlots[theme][chartRoles.other - 1]);
    }
    expect(chartPalette("light").slots).not.toEqual(chartPalette("dark").slots);
  });

  it("ketma-ket shkala: yorug'da kam → och, qorong'ida teskari (ko'p — yorqin)", () => {
    expect(chartPalette("light").sequential).toEqual([...chartSequential]);
    expect(chartPalette("dark").sequential).toEqual([chartSequential[1], chartSequential[0]]);
  });

  it("colorOf: slot 1–8, siyoh, 'Boshqa'; slot oralig'idan tashqari — xato (aylanib takrorlanmaydi)", () => {
    const p = chartPalette("light");
    expect(colorOf(p, 1)).toBe(chartSlots.light[0]);
    expect(colorOf(p, 8)).toBe(chartSlots.light[7]);
    expect(colorOf(p, "ink")).toBe(p.ink);
    expect(colorOf(p, "other")).toBe(p.other);
    expect(() => colorOf(p, 0)).toThrow(RangeError);
    expect(() => colorOf(p, 9)).toThrow(RangeError);
  });

  it("cssColor: legenda CSS o'zgaruvchilarida (mavzu bilan yangilanadi)", () => {
    expect(cssColor(3)).toBe("var(--chart-3)");
    expect(cssColor("ink")).toBe("var(--text-primary)");
    expect(cssColor("other")).toBe("var(--border-input)");
  });
});

describe("tooltip HTML", () => {
  it("foydalanuvchi kiritgan nomlar (do'kon, mahsulot) escape qilinadi", () => {
    expect(escapeHtml(`<img src=x onerror="alert(1)">&'`)).toBe("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;&#39;");
    const html = tooltipHtml("<b>sarlavha</b>", [{ name: "<script>x</script>", value: `"1"`, color: "#fff" }]);
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<b>");
    expect(html).toContain("&lt;script&gt;x&lt;/script&gt;");
    expect(html).toContain("&quot;1&quot;");
  });

  it("rang belgisi yonida, qiymat tabular", () => {
    const html = tooltipHtml("T", [
      { name: "A", value: "1", color: "#111111", shape: "bar" },
      { name: "B", value: "2", color: "#222222", shape: "line" },
      { name: "Jami", value: "3" },
    ]);
    expect(html).toContain("background:#111111");
    expect(html).toContain("height:2px;background:#222222");
    expect(html).toContain("tabular-nums");
    expect(html.match(/<i /g)).toHaveLength(2); // "Jami" belgisiz
  });
});

describe("formatlash yordamchilari", () => {
  it("valueText: asl satrdan aniq; null — tire", () => {
    expect(valueText("money", "2500000.50", f)).toBe(f.money("2500000.50"));
    expect(valueText("money", "2500000.50", f)).toContain(`2${NBSP}500${NBSP}001`); // butun so'mgacha, ROUND_HALF_UP (04 §8.4)
    expect(valueText("count", "1234", f)).toBe(f.number("1234"));
    expect(valueText("money", null, f)).toBe("—");
  });

  it("xText, num", () => {
    expect(xText("day", "2026-10-23", f)).toBe(f.day("2026-10-23"));
    expect(xText("month", "2026-10-01", f)).toBe(f.month("2026-10-01"));
    expect(xText("text", "Tushum", f)).toBe("Tushum");
    expect(num("12.5")).toBe(12.5);
    expect(num(null)).toBeNull();
    expect(num("abc")).toBeNull();
  });
});

describe("lineBarOption (04 §5.1)", () => {
  const build = (series = [REVENUE, PROFIT], over: Partial<Parameters<typeof lineBarOption>[0]> = {}, c = ctx()) =>
    opt(lineBarOption({ x: X, xKind: "day", unit: "money", series, ...over }, c));

  it("bitta o'q: bitta yAxis, ikkinchisi yo'q", () => {
    const o = build();
    expect(Array.isArray(o.yAxis)).toBe(false);
    expect(o.yAxis.type).toBe("value");
  });

  it("ustun: ≤ 24 px, uchi 4 px yumaloq, orasida 2 px fon (1 px ramka × 2); chiziq 2 px, marker ≥ 8 px 2 px halqa bilan", () => {
    const [bar, line] = build().series;
    expect(bar.type).toBe("bar");
    expect(bar.barMaxWidth).toBeLessThanOrEqual(24);
    expect(bar.itemStyle.borderRadius).toEqual([4, 4, 0, 0]);
    expect(bar.itemStyle.borderWidth).toBe(1);
    expect(bar.itemStyle.borderColor).toBe(chartPalette("light").surface);
    expect(line.lineStyle.width).toBe(2);
    expect(line.symbolSize).toBeGreaterThanOrEqual(8);
    expect(line.itemStyle.borderWidth).toBe(2);
    expect(line.itemStyle.borderColor).toBe(chartPalette("light").surface);
  });

  it("seriya ranglari — rol slotlari; natija chizig'i — siyoh", () => {
    const [bar, line] = build().series;
    expect(bar.color).toBe(chartSlots.light[0]);
    expect(line.color).toBe(colors.light["text-primary"]);
    expect(build([REVENUE, PROFIT], {}, ctx({ palette: chartPalette("dark") })).series[0].color).toBe(chartSlots.dark[0]);
  });

  it("markerlar faqat ≤ 14 nuqtada ko'rinadi (aks holda hover'da)", () => {
    expect(build().series[1].showSymbol).toBe(true);
    const many = Array.from({ length: 31 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")}`);
    const o = opt(lineBarOption({ x: many, xKind: "day", unit: "money", series: [{ ...PROFIT, values: many.map(() => "1") }] }, ctx()));
    expect(o.series[0].showSymbol).toBe(false);
  });

  it("to'g'ridan-to'g'ri yorliq: chiziqda va ≤ 4 seriyada; matn seriya rangida emas", () => {
    const line = build().series[1];
    expect(line.endLabel.show).toBe(true);
    expect(line.endLabel.formatter).toBe("Sof foyda");
    expect(line.endLabel.color).toBe(chartPalette("light").textSecondary);
    expect(line.endLabel.color).not.toBe(line.color);
    const five = ["a", "b", "c", "d", "e"].map((k, i) => ({ key: k, name: k, color: i + 1, kind: "line" as const, values: ["1", "2", "3"] }));
    expect(build(five).series.every((s: Any) => !s.endLabel)).toBe(true);
    expect(build([REVENUE]).series[0].endLabel).toBeUndefined();
  });

  it("y o'qi: ustunlarda 0 dan; manfiy qiymat bo'lsa erkin; raqamlar ixcham", () => {
    expect(build([REVENUE]).yAxis.min).toBe(0);
    expect(build().yAxis.min).toBeUndefined(); // foyda manfiy
    const fmt = build().yAxis.axisLabel.formatter as (v: number) => string;
    expect(fmt(0)).toBe("0");
    expect(fmt(500_000)).toBe(f.compact(500_000));
    expect(fmt(1_500_000)).toBe(f.compact(1_500_000));
    expect(f.compact(1_500_000)).toContain("mln");
  });

  it("to'r — hairline, yaxlit (punktir emas); chiziqsiz o'q chizig'i", () => {
    const o = build();
    expect(o.yAxis.splitLine.lineStyle).toMatchObject({ color: chartPalette("light").hairline, type: "solid", width: 1 });
    expect(o.yAxis.axisLine.show).toBe(false);
  });

  it("manfiy ustunning tubi yumaloq", () => {
    const o = build([{ key: "p", name: "P", color: 1, values: ["5", "-3", "2"] }]);
    expect(o.series[0].data[1]).toEqual({ value: -3, itemStyle: { borderRadius: [0, 0, 4, 4] } });
    expect(o.series[0].data[0]).toBe(5);
  });

  it("tooltip: chiziqda crosshair, faqat ustunda soya; hamma seriya qiymati asl satrdan", () => {
    expect(build().tooltip.axisPointer.type).toBe("line");
    expect(build([REVENUE]).tooltip.axisPointer.type).toBe("shadow");
    const html = build().tooltip.formatter([{ dataIndex: 1 }]) as string;
    expect(html).toContain(f.day("2026-10-02"));
    expect(html).toContain("Tushum");
    expect(html).toContain(f.money("2500000.50")); // yaxlitlanmagan — aniq satrdan
    expect(html).toContain("Sof foyda");
    expect(html).toContain(f.money("-50000"));
    const empty = build().tooltip.formatter([{ dataIndex: 2 }]) as string;
    expect(empty).toContain("—"); // tushum null
  });

  it("tooltip seriya nomlarini escape qiladi", () => {
    const html = build([{ ...REVENUE, name: "<img onerror=x>" }]).tooltip.formatter([{ dataIndex: 0 }]) as string;
    expect(html).not.toContain("<img");
  });

  it("annotatsiyalar: faqat birinchi seriyada, soya va shtrix alohida uslubda", () => {
    const o = build([REVENUE, PROFIT], {
      bands: [
        { from: "2026-10-01", to: "2026-10-02", kind: "shade", label: "Bepul logistika" },
        { from: "2026-10-03", to: "2026-10-03", kind: "hatch", label: "Uzilish" },
      ],
    });
    expect(o.series[1].markArea).toBeUndefined();
    const [shade, hatch] = o.series[0].markArea.data;
    expect(shade[0].xAxis).toBe("2026-10-01");
    expect(shade[1].xAxis).toBe("2026-10-02");
    expect(shade[0].itemStyle.color).toBe(chartPalette("light").raised);
    expect(hatch[0].itemStyle.borderType).toBe("dashed");
    expect(o.series[0].markArea.silent).toBe(true);
  });

  it("harakat o'chiq (prefers-reduced-motion) — animatsiya yo'q", () => {
    expect(build([REVENUE], {}, ctx({ motion: false })).animation).toBe(false);
    expect(build([REVENUE]).animation).toBe(true);
  });

  it("x yorlig'i tilga mos (sana, oy)", () => {
    const o = build();
    expect(o.xAxis.data).toEqual(X);
    expect(o.xAxis.axisLabel.formatter("2026-10-03")).toBe(f.day("2026-10-03"));
    const month = opt(lineBarOption({ x: ["2026-10-01"], xKind: "month", unit: "money", series: [REVENUE] }, ctx()));
    expect(month.xAxis.axisLabel.formatter("2026-10-01")).toBe(f.month("2026-10-01"));
  });
});

describe("stackedBarOption", () => {
  const series = [
    { key: "c", name: "Komissiya", color: 2, values: ["10", "0", "5"] },
    { key: "l", name: "Logistika", color: 3, values: ["20", "0", null] },
    { key: "t", name: "Tannarx", color: 4, values: ["0", "0", "30"] },
  ];
  const build = (totals?: Array<string | null>) =>
    opt(stackedBarOption({ x: X, xKind: "day", unit: "money", series, totals, totalLabel: "Jami" }, ctx()));

  it("qatlam: bir stack, 2 px oraliq, faqat eng yuqori segmentning uchi yumaloq", () => {
    const o = build();
    expect(o.series.every((s: Any) => s.stack === "total" && s.type === "bar")).toBe(true);
    expect(o.series[0].itemStyle.borderColor).toBe(chartPalette("light").surface);
    const radius = (s: number, i: number) => o.series[s].data[i].itemStyle.borderRadius;
    expect(radius(1, 0)).toEqual([4, 4, 0, 0]); // 1-ustun: tannarx 0 → logistika yuqorida
    expect(radius(0, 0)).toBe(0);
    expect(radius(2, 2)).toEqual([4, 4, 0, 0]); // 3-ustun: tannarx yuqorida
    expect(radius(0, 2)).toBe(0);
    expect(o.yAxis.min).toBe(0);
  });

  it("tooltip: seriyalar + API'dan kelgan jami (grafik o'zi qo'shmaydi)", () => {
    expect(build().tooltip.formatter([{ dataIndex: 0 }])).not.toContain("Jami");
    const html = build(["30", "0", "35"]).tooltip.formatter([{ dataIndex: 0 }]) as string;
    expect(html).toContain("Jami");
    expect(html).toContain(f.money("30"));
    expect(html).toContain("Komissiya");
  });
});

describe("waterfall", () => {
  const steps: WaterfallStep[] = [
    { key: "rev", label: "Tushum", amount: "1000", kind: "total" },
    { key: "com", label: "Komissiya", amount: "-300", kind: "subtract" },
    { key: "pay", label: "To'lov", amount: "700", kind: "total" },
    { key: "cogs", label: "Tannarx", amount: "-900", kind: "subtract" },
    { key: "net", label: "Foyda", amount: "-200", kind: "total" },
  ];

  it("geometriya: yakuniy ustun 0 dan, ayriluvchi daraja bo'ylab tushadi, nol chizig'idan o'tadi", () => {
    expect(waterfallGeometry(steps)).toEqual([
      [0, 1000, 1000],
      [1000, 700, 700],
      [0, 700, 700],
      [700, -200, -200],
      [0, -200, -200],
    ]);
  });

  it("qo'shiluvchi qadam darajani oshiradi", () => {
    expect(
      waterfallGeometry([
        { key: "a", label: "A", amount: "100", kind: "total" },
        { key: "b", label: "B", amount: "50", kind: "add" },
      ]),
    ).toEqual([
      [0, 100, 100],
      [100, 150, 150],
    ]);
  });

  it("ranglar: qo'shiluvchi — slot 1, ayriluvchi — slot 8, yakuniy — siyoh (holat qizili emas)", () => {
    const o = opt(waterfallOption({ steps: [{ ...steps[0], kind: "add" }, steps[1], steps[2]] }, ctx()));
    const fills = o.series[0].data.map((d: Any) => d.itemStyle.color);
    expect(fills).toEqual([chartSlots.light[0], chartSlots.light[7], colors.light["text-primary"]]);
    expect(fills).not.toContain("#D03B3B");
  });

  it("renderItem: ustun (≤ 24 px, uchi yumaloq, kamida 1 px) va keyingisigacha bog'lovchi chiziq; oxirgisida chiziq yo'q", () => {
    const o = opt(waterfallOption({ steps }, ctx()));
    const data = o.series[0].data as Array<{ value: number[] }>;
    const api = (i: number) => ({
      value: (dim: number) => data[i].value[dim],
      coord: ([x, y]: [number, number]) => [x * 100, 500 - y / 2] as [number, number],
      size: () => [100, 0] as [number, number],
    });
    const first = o.series[0].renderItem(null, api(0));
    expect(first.children).toHaveLength(2);
    const [rect, link] = first.children;
    expect(rect.shape.width).toBe(24);
    expect(rect.shape.r).toEqual([4, 4, 0, 0]);
    expect(rect.shape.height).toBe(500); // 1000 / 2
    expect(rect.style.fill).toBe(chartPalette("light").ink); // yakuniy qadam — siyoh
    expect(link.shape.x1).toBe(rect.shape.x + 24);
    expect(link.shape.y1).toBe(link.shape.y2);
    const last = o.series[0].renderItem(null, api(4));
    expect(last.children).toHaveLength(1);
  });

  it("nol balandlikli qadam ham ko'rinadi (kamida 1 px)", () => {
    const o = opt(waterfallOption({ steps: [{ key: "z", label: "Z", amount: "0", kind: "total" }] }, ctx()));
    const api = {
      value: () => 0,
      coord: () => [10, 100] as [number, number],
      size: () => [100, 0] as [number, number],
    };
    expect(o.series[0].renderItem(null, api).children[0].shape.height).toBe(1);
  });

  it("tor ekranda yorliqlar qiya, keng ekranda qatorga bo'linadi", () => {
    expect(opt(waterfallOption({ steps, compact: true }, ctx())).xAxis.axisLabel).toMatchObject({ rotate: 40, interval: 0 });
    expect(opt(waterfallOption({ steps }, ctx())).xAxis.axisLabel).toMatchObject({ overflow: "break", interval: 0 });
  });

  it("tooltip: qadam nomi va API summasi", () => {
    const o = opt(waterfallOption({ steps }, ctx()));
    const html = o.tooltip.formatter({ dataIndex: 1 }) as string;
    expect(html).toContain("Komissiya");
    expect(html).toContain(f.money("-300"));
  });
});

describe("issiqlik xaritalari", () => {
  const values = Array.from({ length: 7 }, (_, d) => Array.from({ length: 24 }, (_, h) => (h === 14 && d === 2 ? "9" : h === 3 ? null : String(h % 4))));
  const weekdays = weekdayNames(f);

  it("heatmap: bo'sh katak chizilmaydi, dushanba tepada, shkala min–max, tooltip asl qiymat", () => {
    const o = opt(heatmapOption({ values, weekdays, hourLabel, unit: "count", valueLabel: "Buyurtmalar" }, ctx()));
    const data = o.series[0].data as Array<[number, number, number]>;
    expect(data).toHaveLength(7 * 23); // 3-soat — null
    expect(data.some(([h]) => h === 3)).toBe(false);
    expect(o.yAxis.inverse).toBe(true);
    expect(o.yAxis.data).toEqual(weekdays);
    expect(o.visualMap).toMatchObject({ min: 0, max: 9, show: false });
    expect(o.visualMap.inRange.color).toEqual(chartPalette("light").sequential);
    expect(o.series[0].itemStyle.borderWidth).toBe(2);
    const html = o.tooltip.formatter({ value: [14, 2, 9] }) as string;
    expect(html).toContain(`${weekdays[2]}, 14:00`);
    expect(html).toContain("Buyurtmalar");
    expect(html).toContain("9");
  });

  it("hamma qiymat bir xil bo'lsa ham shkala buzilmaydi (max > min)", () => {
    const o = opt(heatmapOption({ values: [["5"]], weekdays: ["Du"], hourLabel, unit: "count", valueLabel: "x" }, ctx()));
    expect(o.visualMap.max).toBeGreaterThan(o.visualMap.min);
  });

  it("kalendar: dushanbadan, oraliq, kun va oy nomlari, tooltip aniq summa", () => {
    const days = [
      { date: "2026-10-01", value: "1500000.50" },
      { date: "2026-10-02", value: null },
      { date: "2026-10-03", value: "300000" },
    ];
    const o = opt(
      calendarHeatmapOption(
        { days, range: ["2026-10-01", "2026-10-03"], weekdaysSunFirst: weekdayNamesSunFirst(f), months: monthNames(f), unit: "money", valueLabel: "Tushum" },
        ctx(),
      ),
    );
    expect(o.calendar.range).toEqual(["2026-10-01", "2026-10-03"]);
    expect(o.calendar.dayLabel.firstDay).toBe(1);
    expect(o.calendar.dayLabel.nameMap[0]).toBe(weekdayNames(f)[6]); // yakshanba birinchi
    expect(o.calendar.monthLabel.nameMap[9]).toBe("oktabr");
    expect(o.series[0].data).toEqual([
      ["2026-10-01", 1500000.5],
      ["2026-10-03", 300000],
    ]);
    const html = o.tooltip.formatter({ value: ["2026-10-01", 1500000.5] }) as string;
    expect(html).toContain(f.day("2026-10-01"));
    expect(html).toContain(f.money("1500000.50"));
    expect(o.tooltip.formatter({ value: ["2026-10-02", 0] })).toContain("—");
  });
});

describe("tavsif va nomlar", () => {
  it("extremes: eng yuqori va past indeks, null'lar hisobga olinmaydi", () => {
    expect(extremes(["5", null, "9", "-2"])).toEqual({ max: 2, min: 3 });
    expect(extremes([null, null])).toBeNull();
    expect(extremes([])).toBeNull();
    expect(extremes(["3"])).toEqual({ max: 0, min: 0 });
  });

  it("describeSeries: nuqta soni va har seriyaning eng yuqori/past qiymati (matnda)", () => {
    const t = ((key: string, p?: Record<string, unknown>) => `${key}:${JSON.stringify(p)}`) as never;
    const text = describeSeries({ x: X, xKind: "day", unit: "money", series: [REVENUE, PROFIT] }, f, t);
    expect(text).toContain('charts.summary.points:{"count":3}');
    expect(text).toContain(`"max":"${f.money("2500000.50")}"`);
    expect(text).toContain(`"at":"${f.day("2026-10-02")}"`);
    expect(text).toContain(`"min":"${f.money("-50000")}"`);
    expect(describeSeries({ x: [], xKind: "day", unit: "money", series: [] }, f, t)).toBe('charts.summary.points:{"count":0}');
  });

  it("hafta kunlari dushanbadan; kalendar uchun yakshanbadan; oylar yilsiz; soat 2 xonali", () => {
    expect(weekdayNames(f)).toEqual(["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]);
    expect(weekdayNamesSunFirst(f)).toEqual(["Ya", "Du", "Se", "Ch", "Pa", "Ju", "Sh"]);
    expect(monthNames(f)).toHaveLength(12);
    expect(monthNames(f).every((m) => !/\d/.test(m))).toBe(true);
    expect(monthNames(formatterFor("ru"))[9]).toBe("октябрь");
    expect(hourLabel(5)).toBe("05:00");
    expect(hourLabel(23)).toBe("23:00");
  });
});
