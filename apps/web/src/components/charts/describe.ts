// Matnli tavsif va nomlar: ekran o'quvchi (`aria-label`) va jadval ko'rinishi uchun — grafik bergan ma'lumotning
// o'zi matnda (04 §11). Qiymatlar asl satrdan formatlanadi.
import type { TFunction } from "i18next";

import type { Formatter } from "../../lib/format";
import { num, valueText, xText } from "./options";
import type { SeriesInput, Unit, XKind } from "./types";

/** Seriya bo'yicha eng yuqori va eng past nuqta (indeks); qiymat yo'q bo'lsa `null`. */
export function extremes(values: Array<string | null>): { max: number; min: number } | null {
  let max = -1;
  let min = -1;
  values.forEach((v, i) => {
    const n = num(v);
    if (n === null) return;
    if (max < 0 || n > num(values[max])!) max = i;
    if (min < 0 || n < num(values[min])!) min = i;
  });
  return max < 0 ? null : { max, min };
}

export function describeSeries(
  input: { x: string[]; xKind: XKind; unit: Unit; series: SeriesInput[] },
  f: Formatter,
  t: TFunction,
): string {
  const { x, xKind, unit, series } = input;
  const parts = series.flatMap((s) => {
    const e = extremes(s.values);
    if (!e) return [];
    return t("charts.summary.series", {
      name: s.name,
      max: valueText(unit, s.values[e.max], f),
      at: xText(xKind, x[e.max], f),
      min: valueText(unit, s.values[e.min], f),
      atMin: xText(xKind, x[e.min], f),
    });
  });
  return [t("charts.summary.points", { count: x.length }), ...parts].join(" ");
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Dushanbadan boshlanadigan qisqa hafta kunlari (2026-10-05 — dushanba). */
export function weekdayNames(f: Formatter): string[] {
  return Array.from({ length: 7 }, (_, i) => f.weekday(`2026-10-${pad(5 + i)}`));
}

/** ECharts kalendari yakshanbadan boshlanuvchi massiv kutadi. */
export function weekdayNamesSunFirst(f: Formatter): string[] {
  const names = weekdayNames(f);
  return [names[6], ...names.slice(0, 6)];
}

/** Oy nomlari (yilsiz): `f.month` "oktabr 2026" qaytaradi. */
export function monthNames(f: Formatter): string[] {
  return Array.from({ length: 12 }, (_, i) => f.month(`2026-${pad(i + 1)}-01`).split(" ")[0]);
}

export const hourLabel = (h: number) => `${pad(h)}:00`;
