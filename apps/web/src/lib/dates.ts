// Sana hisoblari (F1: Toshkent sanasi, UTC+5, yozgi vaqt yo'q) — davr tanlash (DateRangePicker, URL). Sanalar
// "YYYY-MM-DD" satrlarida (API bilan bir xil), vaqt mintaqasi xatolarisiz (UTC kunlar ustida).

export type IsoDate = string;
export type Range = { start: IsoDate; end: IsoDate };
export type Preset = "today" | "yesterday" | "last7" | "last30" | "thisMonth" | "lastMonth" | "thisYear" | "all";
export const PRESETS: readonly Preset[] = ["today", "yesterday", "last7", "last30", "thisMonth", "lastMonth", "thisYear", "all"];

const DAY = 86_400_000;

export function todayTashkent(now: Date = new Date()): IsoDate {
  return new Date(now.getTime() + 5 * 3_600_000).toISOString().slice(0, 10);
}

function toUtc(date: IsoDate): number {
  return Date.parse(`${date}T00:00:00Z`);
}

export function addDays(date: IsoDate, days: number): IsoDate {
  return new Date(toUtc(date) + days * DAY).toISOString().slice(0, 10);
}

export function daysBetween(start: IsoDate, end: IsoDate): number {
  return Math.round((toUtc(end) - toUtc(start)) / DAY);
}

function monthStart(date: IsoDate): IsoDate {
  return `${date.slice(0, 7)}-01`;
}

export function addMonths(date: IsoDate, months: number): IsoDate {
  const d = new Date(toUtc(monthStart(date)));
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}

/** Tayyor davr (04 §5). `all` — eng birinchi ma'lumot sanasidan (`first`) bugungacha. */
export function presetRange(preset: Preset, today: IsoDate, first?: IsoDate): Range {
  switch (preset) {
    case "today":
      return { start: today, end: today };
    case "yesterday": {
      const day = addDays(today, -1);
      return { start: day, end: day };
    }
    case "last7":
      return { start: addDays(today, -6), end: today };
    case "last30":
      return { start: addDays(today, -29), end: today };
    case "thisMonth":
      return { start: monthStart(today), end: today };
    case "lastMonth": {
      const start = addMonths(today, -1);
      return { start, end: addDays(monthStart(today), -1) };
    }
    case "thisYear":
      return { start: `${today.slice(0, 4)}-01-01`, end: today };
    case "all":
      return { start: first ?? `${today.slice(0, 4)}-01-01`, end: today };
  }
}

/** Davr tayyor davrlardan biriga teng bo'lsa — uning nomi. */
export function matchPreset(range: Range, today: IsoDate, first?: IsoDate): Preset | null {
  return PRESETS.find((p) => {
    const r = presetRange(p, today, first);
    return r.start === range.start && r.end === range.end;
  }) ?? null;
}

/** Oldingi davr (F: solishtirish) — shu uzunlikdagi oldingi kunlar; o'tgan yil — bir yil oldin. */
export function previousRange(range: Range, mode: "previous" | "lastYear"): Range {
  if (mode === "lastYear") {
    const shift = (d: IsoDate) => {
      const year = Number(d.slice(0, 4)) - 1;
      const md = d.slice(5) === "02-29" ? "02-28" : d.slice(5);
      return `${year}-${md}`;
    };
    return { start: shift(range.start), end: shift(range.end) };
  }
  const length = daysBetween(range.start, range.end) + 1;
  return { start: addDays(range.start, -length), end: addDays(range.start, -1) };
}

/** Oy kalendari: dushanbadan boshlanadigan haftalar, oy tashqarisidagi kunlar `null`. */
export function monthGrid(month: IsoDate): Array<Array<IsoDate | null>> {
  const first = monthStart(month);
  const next = addMonths(first, 1);
  const offset = (new Date(toUtc(first)).getUTCDay() + 6) % 7;
  const cells: Array<IsoDate | null> = Array.from({ length: offset }, () => null);
  for (let d = first; d < next; d = addDays(d, 1)) cells.push(d);
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

export function isIsoDate(value: unknown): value is IsoDate {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(toUtc(value));
}
